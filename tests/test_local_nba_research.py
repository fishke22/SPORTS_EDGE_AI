from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sports_edge_ai.application.local_nba_research import (
    build_local_nba_training_samples,
    build_nba_feature_from_local_history,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect, migrate

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _seed_game(
    paths: ProjectPaths,
    *,
    event_id: str,
    scheduled_start: datetime,
    result: str,
) -> None:
    connection = connect(paths)
    try:
        observed = scheduled_start - timedelta(days=1)
        result_observed = scheduled_start + timedelta(hours=3)
        decision_observed = scheduled_start - timedelta(hours=7)
        closing_observed = scheduled_start - timedelta(minutes=1)
        connection.execute(
            """
            INSERT INTO canonical_events VALUES (
                ?, 'event-v1', 'NBA', 'NBA', NULL, 'NBA_BOS', 'NBA_NYK',
                ?, NULL, 'FINAL', ?, ?, ?, ?
            )
            """,
            [
                event_id,
                scheduled_start,
                '{"the_odds_api":"' + event_id + '"}',
                observed,
                observed,
                observed + timedelta(seconds=1),
            ],
        )
        for selection in ("HOME", "AWAY"):
            market_id = f"{event_id}:H2H:{selection}"
            connection.execute(
                """
                INSERT INTO canonical_markets VALUES (
                    ?, 'market-v1', ?, 'MONEYLINE', 'FULL_GAME', ?, NULL,
                    'the-odds-api-h2h-v1'
                )
                """,
                [market_id, event_id, selection],
            )
        snapshots = (
            ("HOME", 1.80, decision_observed, "decision-home"),
            ("AWAY", 2.10, decision_observed, "decision-away"),
            ("HOME", 1.75, closing_observed, "closing-home"),
            ("AWAY", 2.20, closing_observed, "closing-away"),
        )
        for selection, odds, observed_at, suffix in snapshots:
            connection.execute(
                """
                INSERT INTO odds_snapshots VALUES (
                    ?, 'odds-v1', ?, ?, 'fixturebook', 'the_odds_api', ?,
                    ?, ?, ?, FALSE, FALSE, ?, ?
                )
                """,
                [
                    f"{event_id}-{suffix}",
                    event_id,
                    f"{event_id}:H2H:{selection}",
                    odds,
                    observed_at,
                    observed_at,
                    observed_at + timedelta(seconds=1),
                    f"data/bronze/the_odds_api/{event_id}.json",
                    (event_id + suffix).encode().hex().ljust(64, "0")[:64],
                ],
            )
        connection.execute(
            """
            INSERT INTO event_results VALUES (
                ?, ?, 'provider_the_odds_api', ?, 110, 100, ?, TRUE,
                ?, ?, ?, ?
            )
            """,
            [
                f"result-{event_id}",
                event_id,
                event_id,
                result,
                result_observed,
                result_observed - timedelta(minutes=5),
                f"data/bronze/the_odds_api/{event_id}-result.json",
                ("result-" + event_id).encode().hex().ljust(64, "0")[:64],
            ],
        )
    finally:
        connection.close()


def test_local_history_builds_point_in_time_elo_and_rest_features(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    first_start = datetime(2026, 9, 20, tzinfo=UTC)
    second_start = datetime(2026, 9, 25, tzinfo=UTC)
    _seed_game(paths, event_id="LOCAL_001", scheduled_start=first_start, result="HOME")
    _seed_game(paths, event_id="LOCAL_002", scheduled_start=second_start, result="AWAY")
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT INTO canonical_events VALUES (
                'CANCELLED_BETWEEN', 'event-v1', 'NBA', 'NBA', NULL,
                'NBA_BOS', 'NBA_NYK', '2026-09-23T00:00:00Z', NULL,
                'CANCELLED', '{"test":"cancelled"}',
                '2026-09-22T00:00:00Z', '2026-09-22T00:00:00Z',
                '2026-09-22T00:00:01Z'
            )
            """
        )
    finally:
        connection.close()

    decision = second_start - timedelta(hours=6)
    feature = build_nba_feature_from_local_history(
        event_id="LOCAL_002",
        decision_as_of=decision,
        paths=paths,
    )

    assert feature.home_rating > 1500.0
    assert feature.away_rating < 1500.0
    assert feature.home_rest_days == 5
    assert feature.away_rest_days == 5
    assert feature.max_input_observed_at <= decision


def test_local_training_dataset_separates_decision_and_closing_odds(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    _seed_game(
        paths,
        event_id="LOCAL_001",
        scheduled_start=datetime(2026, 9, 20, tzinfo=UTC),
        result="HOME",
    )
    _seed_game(
        paths,
        event_id="LOCAL_002",
        scheduled_start=datetime(2026, 9, 25, tzinfo=UTC),
        result="AWAY",
    )

    dataset = build_local_nba_training_samples(
        paths=paths,
        decision_horizon_hours=6,
    )

    assert dataset.candidate_event_count == 2
    assert dataset.skipped_missing_odds == 0
    assert dataset.skipped_non_decisive_result == 0
    assert len(dataset.samples) == 2
    first = dataset.samples[0]
    assert first.home_decimal_odds == 1.80
    assert first.away_decimal_odds == 2.10
    assert first.closing_home_decimal_odds == 1.75
    assert first.closing_away_decimal_odds == 2.20
    assert first.odds_observed_at <= first.features.decision_as_of
    assert first.closing_observed_at >= first.features.decision_as_of
