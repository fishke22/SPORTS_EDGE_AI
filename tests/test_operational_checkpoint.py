from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import current_schema_version, migrate
from sports_edge_ai.infrastructure.operational_checkpoint import (
    OPERATIONAL_CHECKPOINT_ROOTS,
    OPERATIONAL_CHECKPOINT_SCHEMA_VERSION,
    create_operational_checkpoint,
    restore_operational_checkpoint,
    verify_operational_checkpoint,
)

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path, name: str) -> ProjectPaths:
    root = tmp_path / name
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_operational_checkpoint_roundtrip_preserves_point_in_time_roots(
    tmp_path: Path,
) -> None:
    source = _portable_root(tmp_path, "source")
    migrate(source)
    source.ensure_runtime_dirs()
    bronze = source.bronze / "provider" / "raw.json"
    silver = source.silver / "normalized.parquet"
    gold = source.gold / "features.parquet"
    model = source.models / "model.json"
    report = source.reports / "report.json"
    bronze.parent.mkdir(parents=True)
    bronze.write_text('{"raw":"point-in-time"}', encoding="utf-8")
    silver.write_bytes(b"silver")
    gold.write_bytes(b"gold")
    model.write_text('{"model":"research"}', encoding="utf-8")
    report.write_text('{"report":"research"}', encoding="utf-8")
    (source.root / ".env").write_text("SPORTS_EDGE_THE_ODDS_API_KEY=secret\n", encoding="utf-8")

    artifact = create_operational_checkpoint(
        paths=source,
        created_at=datetime(2026, 9, 30, 0, 0, tzinfo=UTC),
    )
    archive_path = source.root / artifact.relative_path
    verification = verify_operational_checkpoint(archive_path)

    assert verification.source_schema_version == "0009"
    assert verification.includes_raw_data is True
    assert verification.public_export_allowed is False
    assert verification.secret_transport is False
    assert artifact.file_count == verification.file_count
    assert artifact.total_bytes == verification.total_bytes
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "data/bronze/provider/raw.json" in names
        assert "data/silver/normalized.parquet" in names
        assert "data/gold/features.parquet" in names
        assert "state/sports_edge.duckdb" in names
        assert ".env" not in names
        assert not any(name.startswith("backups/") for name in names)

    target = _portable_root(tmp_path, "target")
    target.ensure_runtime_dirs()
    restored = restore_operational_checkpoint(archive_path, paths=target)

    assert restored.source_schema_version == "0009"
    assert current_schema_version(target) == "0009"
    assert (target.bronze / "provider" / "raw.json").read_text(encoding="utf-8") == (
        '{"raw":"point-in-time"}'
    )
    assert (target.silver / "normalized.parquet").read_bytes() == b"silver"
    assert (target.gold / "features.parquet").read_bytes() == b"gold"
    assert (target.models / "model.json").read_text(encoding="utf-8") == (
        '{"model":"research"}'
    )


def test_operational_checkpoint_restore_refuses_nonempty_runtime(tmp_path: Path) -> None:
    source = _portable_root(tmp_path, "source")
    migrate(source)
    artifact = create_operational_checkpoint(paths=source)
    archive_path = source.root / artifact.relative_path

    target = _portable_root(tmp_path, "target")
    target.ensure_runtime_dirs()
    (target.bronze / "existing.json").write_text("existing", encoding="utf-8")

    with pytest.raises(RuntimeError, match="empty runtime target"):
        restore_operational_checkpoint(archive_path, paths=target)


def test_operational_checkpoint_verification_rejects_undeclared_entry(tmp_path: Path) -> None:
    source = _portable_root(tmp_path, "source")
    migrate(source)
    artifact = create_operational_checkpoint(paths=source)
    archive_path = source.root / artifact.relative_path

    with zipfile.ZipFile(archive_path, mode="a") as archive:
        archive.writestr("unexpected.txt", b"unexpected")

    with pytest.raises(ValueError, match="undeclared archive entries"):
        verify_operational_checkpoint(archive_path)


def test_operational_checkpoint_rejects_configured_secret_leakage(tmp_path: Path) -> None:
    source = _portable_root(tmp_path, "source")
    migrate(source)
    source.ensure_runtime_dirs()
    secret = "never-export-this-provider-key-123456"
    (source.root / ".env").write_text(
        f"SPORTS_EDGE_THE_ODDS_API_KEY={secret}\n",
        encoding="utf-8",
    )
    leaked_report = source.reports / "bad-report.txt"
    leaked_report.write_text(f"credential={secret}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="configured credential leaked"):
        create_operational_checkpoint(paths=source)

    checkpoint_dir = source.backups / "operational-checkpoints"
    assert not checkpoint_dir.exists() or not tuple(checkpoint_dir.glob("*.zip"))


def test_operational_checkpoint_rejects_noncanonical_windows_like_path(tmp_path: Path) -> None:
    source = _portable_root(tmp_path, "source")
    migrate(source)
    malicious = tmp_path / "malicious.zip"
    payload = b"escape"
    relative = "state/nested\\..\\escape.bin"
    manifest = {
        "schema_version": OPERATIONAL_CHECKPOINT_SCHEMA_VERSION,
        "created_at": datetime(2026, 9, 30, 0, 0, tzinfo=UTC).isoformat(),
        "source_schema_version": "0009",
        "includes_raw_data": True,
        "public_export_allowed": False,
        "secret_transport": False,
        "allowed_roots": list(OPERATIONAL_CHECKPOINT_ROOTS),
        "file_count": 1,
        "total_bytes": len(payload),
        "files": [
            {
                "relative_path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        ],
    }
    with zipfile.ZipFile(malicious, mode="w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        archive.writestr(relative, payload)

    with pytest.raises(ValueError, match="disallowed path"):
        verify_operational_checkpoint(malicious)


def test_operational_checkpoint_restore_rolls_back_on_migration_checksum_mismatch(
    tmp_path: Path,
) -> None:
    source = _portable_root(tmp_path, "source")
    migrate(source)
    source.ensure_runtime_dirs()
    (source.bronze / "evidence.json").write_text("evidence", encoding="utf-8")
    artifact = create_operational_checkpoint(paths=source)
    archive_path = source.root / artifact.relative_path

    target = _portable_root(tmp_path, "target")
    target.ensure_runtime_dirs()
    first_migration = sorted((target.root / "sql" / "migrations").glob("*.sql"))[0]
    first_migration.write_text(
        first_migration.read_text(encoding="utf-8") + "\n-- tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="checksum differs"):
        restore_operational_checkpoint(archive_path, paths=target)

    assert not target.database.exists()
    assert not (target.bronze / "evidence.json").exists()
