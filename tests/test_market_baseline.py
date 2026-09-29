from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_edge_ai.application.market_baseline import (
    build_market_baseline,
    ensure_point_in_time,
)
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.odds_repository import MarketOddsAsOf

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _fixture(name: str) -> Path:
    return PROJECT_ROOT / "fixtures" / "synthetic" / name


def test_gold_market_baseline_uses_only_as_of_odds(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)
    ingest_synthetic_snapshot(
        _fixture("nba_moneyline_snapshot_later.json"),
        paths=paths,
    )

    decision_as_of = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    dataset = build_market_baseline(
        event_id="SYNTH_NBA_001",
        decision_as_of=decision_as_of,
        paths=paths,
    )

    assert dataset.relative_path is not None
    assert (paths.root / dataset.relative_path).is_file()
    assert len(dataset.records) == 2
    by_selection = {row.selection: row for row in dataset.records}
    assert by_selection["HOME"].decimal_odds == pytest.approx(1.80)
    assert by_selection["AWAY"].decimal_odds == pytest.approx(2.10)
    assert sum(row.market_probability_fair for row in dataset.records) == pytest.approx(1.0)
    assert sum(row.market_probability_raw for row in dataset.records) > 1.0
    assert all(row.max_input_observed_at <= decision_as_of for row in dataset.records)
    assert all(row.decision_as_of == decision_as_of for row in dataset.records)
    assert all(row.gross_ev_baseline < 0.0 for row in dataset.records)


def test_point_in_time_hard_gate_rejects_future_input() -> None:
    decision_as_of = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    future_row = MarketOddsAsOf(
        market_id="SYNTH_NBA_001_ML:HOME",
        market_type="MONEYLINE",
        period="FULL_GAME",
        selection="HOME",
        bookmaker="SYNTHETIC_BOOK",
        source="synthetic_nba",
        decimal_odds=1.75,
        observed_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        provider_timestamp=None,
        raw_source_ref="data/bronze/synthetic/example.json",
        payload_hash="0" * 64,
    )

    with pytest.raises(RuntimeError, match="point-in-time violation"):
        ensure_point_in_time((future_row,), decision_as_of)
