from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_edge_ai.application.paper_trading import (
    open_paper_trade,
    settle_open_paper_trades,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    EventResultRecord,
    ModelRegistryRecord,
    PredictionRecord,
    Recommendation,
)
from sports_edge_ai.infrastructure.db import connect, migrate
from sports_edge_ai.infrastructure.model_repository import persist_model_registry_record
from sports_edge_ai.infrastructure.paper_trade_repository import get_settlement_for_trade
from sports_edge_ai.infrastructure.result_repository import persist_event_results

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _seed_market(paths: ProjectPaths) -> tuple[str, str, str]:
    migrate(paths)
    event_id = "NBA_PAPER_TEST"
    market_id = f"{event_id}:H2H:HOME"
    snapshot_id = "odds-paper-test"
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT INTO canonical_events VALUES (
                ?, 'event-v1', 'NBA', 'NBA', NULL, 'NBA_BOS', 'NBA_NYK',
                '2026-09-29T00:00:00Z', NULL, 'SCHEDULED',
                '{"the_odds_api":"paper_provider_event"}',
                '2026-09-28T06:59:00Z', '2026-09-28T06:59:00Z',
                '2026-09-28T06:59:01Z'
            )
            """,
            [event_id],
        )
        connection.execute(
            """
            INSERT INTO canonical_markets VALUES (
                ?, 'market-v1', ?, 'MONEYLINE', 'FULL_GAME',
                'HOME', NULL, 'the-odds-api-h2h-v1'
            )
            """,
            [market_id, event_id],
        )
        connection.execute(
            """
            INSERT INTO odds_snapshots VALUES (
                ?, 'odds-v1', ?, ?, 'fixturebook', 'the_odds_api', 1.75,
                '2026-09-28T06:59:00Z', '2026-09-28T06:58:30Z',
                '2026-09-28T06:59:01Z', FALSE, FALSE,
                'data/bronze/the_odds_api/test.json',
                ?
            )
            """,
            [snapshot_id, event_id, market_id, "b" * 64],
        )
    finally:
        connection.close()
    return event_id, market_id, snapshot_id


def _model(paths: ProjectPaths, *, status: str, model_id: str) -> None:
    persist_model_registry_record(
        ModelRegistryRecord(
            model_id=model_id,
            model_version="v1",
            sport="NBA",
            market_type="MONEYLINE",
            training_window_start=datetime(2026, 1, 1, tzinfo=UTC),
            training_window_end=datetime(2026, 6, 1, tzinfo=UTC),
            validation_window_start=datetime(2026, 6, 2, tzinfo=UTC),
            validation_window_end=datetime(2026, 7, 1, tzinfo=UTC),
            feature_version="features-v1",
            calibration_version="cal-v1",
            artifact_path=f"models/{model_id}/v1.json",
            artifact_sha256="a" * 64,
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
            status=status,
            metrics_json={"source": "test"},
        ),
        paths=paths,
    )


def _prediction(
    *,
    event_id: str,
    market_id: str,
    model_id: str,
    recommendation: Recommendation = Recommendation.EDGE,
) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=f"prediction-{model_id}-{recommendation.value}",
        event_id=event_id,
        market_id=market_id,
        model_id=model_id,
        model_version="v1",
        feature_version="features-v1",
        calibration_version="cal-v1",
        model_probability_raw=0.65,
        model_probability_calibrated=0.64,
        market_probability_raw=0.58,
        market_probability_fair=0.57,
        fair_odds=1.5625,
        edge=0.07,
        gross_ev=0.12,
        net_ev=0.10,
        uncertainty=0.05,
        data_quality=DataQualityStatus.GREEN,
        recommendation=recommendation,
        generated_at=datetime(2026, 9, 28, 6, 59, 30, tzinfo=UTC),
        as_of=datetime(2026, 9, 28, 7, 0, tzinfo=UTC),
    )


def test_validated_edge_opens_and_settles_paper_trade(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    event_id, market_id, snapshot_id = _seed_market(paths)
    _model(paths, status="VALIDATED", model_id="validated-model")
    prediction = _prediction(
        event_id=event_id,
        market_id=market_id,
        model_id="validated-model",
    )

    trade = open_paper_trade(
        prediction=prediction,
        odds_snapshot_id=snapshot_id,
        stake=1.0,
        paths=paths,
    )

    assert trade.status == "OPEN"
    assert trade.odds_decimal == 1.75

    persist_event_results(
        (
            EventResultRecord(
                event_result_id="result-paper-test",
                event_id=event_id,
                provider_id="provider_the_odds_api",
                provider_event_id="paper_provider_event",
                home_score=112,
                away_score=104,
                result_outcome="HOME",
                completed=True,
                observed_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
                provider_timestamp=datetime(2026, 9, 29, 2, 40, tzinfo=UTC),
                raw_source_ref="data/bronze/the_odds_api/result.json",
                payload_hash="c" * 64,
            ),
        ),
        paths=paths,
    )
    settlements = settle_open_paper_trades(
        event_id=event_id,
        settled_at=datetime(2026, 9, 29, 3, 1, tzinfo=UTC),
        paths=paths,
    )

    assert len(settlements) == 1
    assert settlements[0].settlement_status == "WIN"
    assert settlements[0].gross_payout == pytest.approx(1.75)
    assert settlements[0].pnl == pytest.approx(0.75)
    stored = get_settlement_for_trade(paper_trade_id=trade.paper_trade_id, paths=paths)
    assert stored == settlements[0]

    connection = connect(paths)
    try:
        status = connection.execute(
            "SELECT status FROM paper_trades WHERE paper_trade_id = ?",
            [trade.paper_trade_id],
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "SETTLED"


def test_unvalidated_model_cannot_open_paper_trade(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    event_id, market_id, snapshot_id = _seed_market(paths)
    _model(paths, status="RESEARCH_NOT_VALIDATED", model_id="research-model")

    with pytest.raises(ValueError, match="status VALIDATED"):
        open_paper_trade(
            prediction=_prediction(
                event_id=event_id,
                market_id=market_id,
                model_id="research-model",
            ),
            odds_snapshot_id=snapshot_id,
            stake=1.0,
            paths=paths,
        )


def test_non_edge_recommendation_cannot_open_paper_trade(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    event_id, market_id, snapshot_id = _seed_market(paths)
    _model(paths, status="VALIDATED", model_id="validated-model")

    with pytest.raises(ValueError, match="requires EDGE"):
        open_paper_trade(
            prediction=_prediction(
                event_id=event_id,
                market_id=market_id,
                model_id="validated-model",
                recommendation=Recommendation.NO_VALIDATED_EDGE,
            ),
            odds_snapshot_id=snapshot_id,
            stake=1.0,
            paths=paths,
        )


def test_unknown_paper_settlement_rule_is_fail_closed(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    event_id, market_id, snapshot_id = _seed_market(paths)
    _model(paths, status="VALIDATED", model_id="validated-model")
    trade = open_paper_trade(
        prediction=_prediction(
            event_id=event_id,
            market_id=market_id,
            model_id="validated-model",
        ),
        odds_snapshot_id=snapshot_id,
        stake=1.0,
        settlement_rule_version="unknown-rule-v1",
        paths=paths,
    )
    persist_event_results(
        (
            EventResultRecord(
                event_result_id="result-unknown-rule",
                event_id=event_id,
                provider_id="provider_the_odds_api",
                provider_event_id="paper_provider_event",
                home_score=112,
                away_score=104,
                result_outcome="HOME",
                completed=True,
                observed_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
                provider_timestamp=datetime(2026, 9, 29, 2, 40, tzinfo=UTC),
                raw_source_ref="data/bronze/the_odds_api/result.json",
                payload_hash="d" * 64,
            ),
        ),
        paths=paths,
    )

    with pytest.raises(ValueError, match="unsupported paper settlement rule"):
        settle_open_paper_trades(
            event_id=trade.event_id,
            settled_at=datetime(2026, 9, 29, 3, 1, tzinfo=UTC),
            paths=paths,
        )
