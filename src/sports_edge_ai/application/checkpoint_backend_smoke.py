from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from sports_edge_ai.application.checkpoint_backend import assess_zero_cost_backend
from sports_edge_ai.common.root import ROOT_MARKER, ProjectPaths
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.local_checkpoint_backend import (
    LocalFilesystemCheckpointBackend,
)
from sports_edge_ai.infrastructure.operational_checkpoint import (
    create_operational_checkpoint,
    restore_operational_checkpoint,
)


@dataclass(frozen=True, slots=True)
class CheckpointBackendSmokeResult:
    status: str
    backend_id: str
    remote_live_eligible: bool
    blockers: tuple[str, ...]
    checkpoint_sha256: str
    generation: str
    restored_marker: str


def _portable_root(source_root: Path, target_root: Path) -> ProjectPaths:
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / ROOT_MARKER).write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    shutil.copytree(source_root / "sql" / "migrations", target_root / "sql" / "migrations")
    return ProjectPaths(target_root)


def run_checkpoint_backend_contract_smoke(
    *,
    source_paths: ProjectPaths | None = None,
) -> CheckpointBackendSmokeResult:
    source = source_paths or ProjectPaths.discover()
    with TemporaryDirectory(prefix="sports-edge-backend-smoke-") as temporary:
        root = Path(temporary)
        runtime = _portable_root(source.root, root / "runtime")
        migrate(runtime)
        runtime.ensure_runtime_dirs()
        marker = "phase14-point-in-time-marker"
        (runtime.bronze / "contract-marker.txt").write_text(marker, encoding="utf-8")

        artifact = create_operational_checkpoint(paths=runtime)
        archive = runtime.root / artifact.relative_path
        backend = LocalFilesystemCheckpointBackend(root / "backend")
        assessment = assess_zero_cost_backend(backend.capabilities)
        stored = backend.publish(archive, expected_generation=None)

        download_dir = root / "download"
        downloaded = backend.fetch_latest(download_dir)
        restored = _portable_root(source.root, root / "restored")
        restored.ensure_runtime_dirs()
        restore_operational_checkpoint(downloaded, paths=restored)
        restored_marker = (restored.bronze / "contract-marker.txt").read_text(encoding="utf-8")

        if restored_marker != marker:
            raise RuntimeError("checkpoint backend round-trip marker mismatch")
        if assessment.remote_live_eligible:
            raise RuntimeError("reference backend must never be remote-live eligible")

        return CheckpointBackendSmokeResult(
            status="PASS",
            backend_id=backend.capabilities.backend_id,
            remote_live_eligible=assessment.remote_live_eligible,
            blockers=assessment.blockers,
            checkpoint_sha256=artifact.sha256,
            generation=stored.generation,
            restored_marker=restored_marker,
        )
