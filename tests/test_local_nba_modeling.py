from __future__ import annotations

import shutil
from pathlib import Path

from sports_edge_ai.application.local_nba_modeling import evaluate_local_nba_research
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import migrate

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_local_nba_modeling_fails_closed_when_history_is_insufficient(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)

    result = evaluate_local_nba_research(
        paths=paths,
        min_train_size=4,
        test_size=2,
        calibration_size=2,
        bootstrap_iterations=20,
    )

    assert result.status == "INSUFFICIENT_DATA"
    assert result.dataset.samples == ()
    assert result.evaluation is None
    assert result.validation is None
