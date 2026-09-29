from pathlib import Path

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect, migrate


def test_migration_is_versioned_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "portable-db"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")

    source = Path(__file__).parents[1] / "sql" / "migrations" / "0001_foundation.sql"
    (migrations / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    paths = ProjectPaths(root)
    first = migrate(paths)
    second = migrate(paths)

    assert first.applied == ("0001",)
    assert second.applied == ()
    assert second.current_version == "0001"

    connection = connect(paths)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "canonical_events",
        "canonical_markets",
        "odds_snapshots",
        "predictions",
        "model_registry",
        "backtest_runs",
        "paper_trades",
        "settlements",
        "risk_assessments",
        "data_quality",
    }.issubset(tables)
