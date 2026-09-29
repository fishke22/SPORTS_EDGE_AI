from __future__ import annotations

import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.backup import (
    create_research_backup,
    restore_research_backup,
)
from sports_edge_ai.infrastructure.db import current_schema_version, migrate

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_research_backup_excludes_raw_data_and_restores_state(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    paths.ensure_runtime_dirs()
    model_file = paths.models / "model.json"
    report_file = paths.reports / "report.json"
    config_file = paths.config / "runtime.json"
    raw_file = paths.bronze / "licensed.json"
    model_file.write_text('{"model":"ok"}', encoding="utf-8")
    report_file.write_text('{"report":"ok"}', encoding="utf-8")
    config_file.write_text('{"config":"ok"}', encoding="utf-8")
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text('{"licensed":"raw"}', encoding="utf-8")

    artifact = create_research_backup(
        paths=paths,
        created_at=datetime(2026, 9, 28, 7, tzinfo=UTC),
    )
    backup_path = paths.root / artifact.relative_path

    assert backup_path.is_file()
    with zipfile.ZipFile(backup_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "models/model.json" in names
        assert "reports/report.json" in names
        assert "config/runtime.json" in names
        assert not any(name.startswith("data/") for name in names)

    model_file.unlink()
    report_file.unlink()
    config_file.unlink()
    paths.database.unlink()
    assert current_schema_version(paths) is None

    restored = restore_research_backup(backup_path, paths=paths, force=True)

    assert "state/sports_edge.duckdb" in restored.restored_files
    assert model_file.read_text(encoding="utf-8") == '{"model":"ok"}'
    assert report_file.read_text(encoding="utf-8") == '{"report":"ok"}'
    assert config_file.read_text(encoding="utf-8") == '{"config":"ok"}'
    assert current_schema_version(paths) == "0009"
    assert raw_file.read_text(encoding="utf-8") == '{"licensed":"raw"}'


def test_restore_requires_explicit_force(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    artifact = create_research_backup(paths=paths)
    backup_path = paths.root / artifact.relative_path

    with pytest.raises(ValueError, match="force=True"):
        restore_research_backup(backup_path, paths=paths)
