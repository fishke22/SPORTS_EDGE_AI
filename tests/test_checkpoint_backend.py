from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_edge_ai.application.checkpoint_backend import (
    CheckpointBackendBusyError,
    CheckpointBackendCapabilities,
    CheckpointBackendConflictError,
    CheckpointBackendQuotaError,
    assess_zero_cost_backend,
)
from sports_edge_ai.application.checkpoint_backend_smoke import (
    run_checkpoint_backend_contract_smoke,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.local_checkpoint_backend import (
    LocalFilesystemCheckpointBackend,
)
from sports_edge_ai.infrastructure.operational_checkpoint import (
    create_operational_checkpoint,
    restore_operational_checkpoint,
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


def _checkpoint(
    paths: ProjectPaths,
    marker: str,
    *,
    created_at: datetime,
) -> Path:
    if not paths.database.exists():
        migrate(paths)
    paths.ensure_runtime_dirs()
    (paths.bronze / "marker.txt").write_text(marker, encoding="utf-8")
    artifact = create_operational_checkpoint(paths=paths, created_at=created_at)
    return paths.root / artifact.relative_path


def test_reference_backend_capabilities_are_never_remote_live_eligible(tmp_path: Path) -> None:
    backend = LocalFilesystemCheckpointBackend(tmp_path / "backend")

    assessment = assess_zero_cost_backend(backend.capabilities)

    assert assessment.remote_live_eligible is False
    assert "NO_REMOTE_ACCESS" in assessment.blockers
    assert "REFERENCE_ONLY_BACKEND" in assessment.blockers
    assert backend.capabilities.automatic_billing_possible is False


def test_capability_evaluator_accepts_only_complete_zero_cost_remote_contract() -> None:
    capabilities = CheckpointBackendCapabilities(
        backend_id="synthetic-complete-remote-v1",
        private_storage=True,
        durable_storage=True,
        automatic_billing_possible=False,
        atomic_publish=True,
        versioned_objects=True,
        single_writer_guard=True,
        quota_fail_closed=True,
        secret_separation=True,
        portable_export=True,
        remote_access=True,
        reference_only=False,
    )

    assessment = assess_zero_cost_backend(capabilities)

    assert assessment.remote_live_eligible is True
    assert assessment.blockers == ()


def test_reference_backend_roundtrip_preserves_checkpoint(tmp_path: Path) -> None:
    source = _portable_root(tmp_path, "source")
    archive = _checkpoint(
        source,
        "roundtrip",
        created_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
    )
    backend = LocalFilesystemCheckpointBackend(tmp_path / "backend")

    stored = backend.publish(archive, expected_generation=None)
    downloaded = backend.fetch_latest(tmp_path / "downloads")
    target = _portable_root(tmp_path, "target")
    target.ensure_runtime_dirs()
    restore_operational_checkpoint(downloaded, paths=target)

    assert stored.generation == stored.sha256
    assert backend.latest() == stored
    assert (target.bronze / "marker.txt").read_text(encoding="utf-8") == "roundtrip"


def test_reference_backend_rejects_stale_generation_without_changing_current(
    tmp_path: Path,
) -> None:
    source = _portable_root(tmp_path, "source")
    first = _checkpoint(
        source,
        "first",
        created_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
    )
    backend = LocalFilesystemCheckpointBackend(tmp_path / "backend")
    first_stored = backend.publish(first, expected_generation=None)

    second = _checkpoint(
        source,
        "second",
        created_at=datetime(2026, 9, 30, 12, 1, tzinfo=UTC),
    )
    with pytest.raises(CheckpointBackendConflictError, match="generation changed"):
        backend.publish(second, expected_generation="0" * 64)

    assert backend.latest() == first_stored


def test_reference_backend_rejects_second_writer_lock(tmp_path: Path) -> None:
    source = _portable_root(tmp_path, "source")
    archive = _checkpoint(
        source,
        "lock",
        created_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
    )
    backend = LocalFilesystemCheckpointBackend(tmp_path / "backend")
    backend.root.mkdir(parents=True)
    backend._lock.write_text("held", encoding="utf-8")

    with pytest.raises(CheckpointBackendBusyError, match="writer lock"):
        backend.publish(archive, expected_generation=None)

    assert backend._pointer.exists() is False
    assert backend._lock.read_text(encoding="utf-8") == "held"


def test_reference_backend_quota_failure_does_not_publish_or_delete_history(
    tmp_path: Path,
) -> None:
    source = _portable_root(tmp_path, "source")
    first = _checkpoint(
        source,
        "first",
        created_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
    )
    backend_root = tmp_path / "backend"
    backend = LocalFilesystemCheckpointBackend(backend_root, quota_bytes=10_000_000)
    first_stored = backend.publish(first, expected_generation=None)
    existing_objects = tuple(sorted(path.name for path in (backend_root / "objects").glob("*.zip")))

    second = _checkpoint(
        source,
        "second-with-more-data",
        created_at=datetime(2026, 9, 30, 12, 1, tzinfo=UTC),
    )
    used = sum(path.stat().st_size for path in (backend_root / "objects").glob("*.zip"))
    second_bytes = second.stat().st_size
    limited = LocalFilesystemCheckpointBackend(
        backend_root,
        quota_bytes=used + second_bytes - 1,
    )

    with pytest.raises(CheckpointBackendQuotaError, match="free quota"):
        limited.publish(second, expected_generation=first_stored.generation)

    assert limited.latest() == first_stored
    assert tuple(sorted(path.name for path in (backend_root / "objects").glob("*.zip"))) == (
        existing_objects
    )


def test_checkpoint_backend_contract_smoke_is_reference_only() -> None:
    result = run_checkpoint_backend_contract_smoke()

    assert result.status == "PASS"
    assert result.backend_id == "local-filesystem-reference-v1"
    assert result.remote_live_eligible is False
    assert "NO_REMOTE_ACCESS" in result.blockers
    assert "REFERENCE_ONLY_BACKEND" in result.blockers
    assert result.restored_marker == "phase14-point-in-time-marker"
