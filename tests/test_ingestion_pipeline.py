from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect
from sports_edge_ai.infrastructure.odds_repository import get_event_odds_as_of

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    (root / "sql" / "migrations").mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, root / "sql" / "migrations" / migration.name)
    return ProjectPaths(root)


def _fixture(name: str) -> Path:
    return PROJECT_ROOT / "fixtures" / "synthetic" / name


def test_ingest_writes_immutable_bronze_silver_and_duckdb(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    first = ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)
    repeated = ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)

    assert first.bronze == repeated.bronze
    assert not Path(first.bronze.relative_path).is_absolute()
    assert (paths.root / first.bronze.relative_path).is_file()
    assert (paths.root / first.bronze.manifest_relative_path).is_file()
    assert all((paths.root / relative).is_file() for relative in first.silver_paths)

    manifest = json.loads(
        (paths.root / first.bronze.manifest_relative_path).read_text(encoding="utf-8")
    )
    assert not Path(manifest["relative_path"]).is_absolute()
    assert ":" not in manifest["relative_path"].split("/", 1)[0]

    connection = connect(paths)
    try:
        counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "raw_objects",
                "ingest_runs",
                "canonical_events",
                "canonical_markets",
                "odds_snapshots",
            )
        }
    finally:
        connection.close()

    assert counts == {
        "raw_objects": 1,
        "ingest_runs": 1,
        "canonical_events": 1,
        "canonical_markets": 2,
        "odds_snapshots": 2,
    }


def test_as_of_query_never_uses_future_snapshot(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot.json"), paths=paths)
    ingest_synthetic_snapshot(_fixture("nba_moneyline_snapshot_later.json"), paths=paths)

    before = get_event_odds_as_of(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 7, 59, tzinfo=UTC),
        paths=paths,
    )
    middle = get_event_odds_as_of(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
        paths=paths,
    )
    after = get_event_odds_as_of(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 9, 30, tzinfo=UTC),
        paths=paths,
    )

    assert before == ()
    middle_prices = {row.market_id.rsplit(":", 1)[-1]: row.decimal_odds for row in middle}
    after_prices = {row.market_id.rsplit(":", 1)[-1]: row.decimal_odds for row in after}
    assert middle_prices == {"AWAY": 2.10, "HOME": 1.80}
    assert after_prices == {"AWAY": 2.20, "HOME": 1.75}
    assert all(row.observed_at <= datetime(2026, 10, 1, 8, 30, tzinfo=UTC) for row in middle)
