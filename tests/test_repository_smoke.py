from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from sports_edge_ai.application.repository_smoke import run_repository_smoke
from sports_edge_ai.common.root import ProjectPaths

PROJECT_ROOT = Path(__file__).parents[1]


def _minimal_checkout(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "checkout"
    (root / "fixtures").mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    shutil.copytree(PROJECT_ROOT / "sql", root / "sql")
    shutil.copytree(PROJECT_ROOT / "fixtures" / "synthetic", root / "fixtures" / "synthetic")
    return ProjectPaths(root)


def test_repository_smoke_is_offline_ephemeral_and_fail_closed(tmp_path: Path) -> None:
    source_paths = _minimal_checkout(tmp_path)

    result = run_repository_smoke(source_paths=source_paths)

    assert result.status == "PASS"
    assert result.mode == "OFFLINE_SYNTHETIC_EPHEMERAL"
    assert result.schema_version == "0009"
    assert result.decision_as_of == datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    assert result.max_input_observed_at == datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    assert result.baseline_odds == (("AWAY", 2.10), ("HOME", 1.80))
    assert "NO_VALIDATED_EDGE" in result.recommendations
    assert "EDGE" not in result.recommendations
    assert result.validated_edge_claimed is False
    assert result.network_required is False
    assert result.credentials_required is False
    assert result.persistent_state_required is False
    assert "MODEL_NOT_VALIDATED" in result.risk_blockers
    assert not source_paths.database.exists()
    assert not source_paths.bronze.exists()
