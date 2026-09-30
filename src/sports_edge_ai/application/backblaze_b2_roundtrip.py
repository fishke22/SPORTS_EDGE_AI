from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from sports_edge_ai.common.root import ROOT_MARKER, ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.operational_checkpoint import (
    create_operational_checkpoint,
    restore_operational_checkpoint,
    verify_operational_checkpoint,
)
from sports_edge_ai.infrastructure.providers.backblaze_b2 import (
    B2Transport,
    BackblazeB2CheckpointBackend,
)

B2_ROUND_TRIP_MARKER = "phase16b-backblaze-b2-roundtrip-marker"


@dataclass(frozen=True, slots=True)
class BackblazeB2RoundTripResult:
    status: str
    checkpoint_sha256: str
    generation: str
    bytes: int
    restored_marker: str
    cas_conflict_verified: bool
    remote_live_ready: bool
    blockers: tuple[str, ...]


def _portable_root(source_root: Path, target_root: Path) -> ProjectPaths:
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / ROOT_MARKER).write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    shutil.copytree(source_root / "sql" / "migrations", target_root / "sql" / "migrations")
    return ProjectPaths(target_root)


def run_backblaze_b2_live_roundtrip(
    *,
    settings: Settings | None = None,
    transport: B2Transport | None = None,
    source_paths: ProjectPaths | None = None,
) -> BackblazeB2RoundTripResult:
    source = source_paths or ProjectPaths.discover()
    effective_settings = settings or Settings(project_root=source.root)
    backend = BackblazeB2CheckpointBackend(
        settings=effective_settings,
        transport=transport,
    )

    preflight = backend.preflight(provider_round_trip_verified=False)
    if not preflight.storage_operations_allowed:
        raise RuntimeError(
            "Backblaze B2 live round-trip blocked by preflight: "
            + ",".join(preflight.blockers)
        )

    if backend.latest() is not None:
        raise RuntimeError(
            "Backblaze B2 live round-trip requires an empty checkpoint bucket "
            "with no current pointer"
        )

    with TemporaryDirectory(prefix="sports-edge-b2-roundtrip-") as temporary:
        root = Path(temporary)
        runtime = _portable_root(source.root, root / "runtime")
        migrate(runtime)
        runtime.ensure_runtime_dirs()
        (runtime.bronze / "b2-roundtrip-marker.txt").write_text(
            B2_ROUND_TRIP_MARKER,
            encoding="utf-8",
        )

        artifact = create_operational_checkpoint(paths=runtime)
        archive = runtime.root / artifact.relative_path
        stored = backend.publish(archive, expected_generation=None)

        current = backend.latest()
        if current != stored:
            raise RuntimeError("Backblaze B2 current pointer does not match published checkpoint")

        downloaded = backend.fetch_latest(root / "downloads")
        downloaded_verification = verify_operational_checkpoint(downloaded)
        if downloaded_verification.sha256 != stored.sha256:
            raise RuntimeError("Backblaze B2 round-trip checkpoint hash mismatch")

        restored = _portable_root(source.root, root / "restored")
        restored.ensure_runtime_dirs()
        restore_operational_checkpoint(downloaded, paths=restored)
        restored_marker = (restored.bronze / "b2-roundtrip-marker.txt").read_text(
            encoding="utf-8"
        )
        if restored_marker != B2_ROUND_TRIP_MARKER:
            raise RuntimeError("Backblaze B2 round-trip restore marker mismatch")

        backend.verify_stale_revision_conflict()
        final = backend.preflight(provider_round_trip_verified=True)
        if not final.remote_live_ready:
            raise RuntimeError(
                "Backblaze B2 round-trip completed but final preflight is blocked: "
                + ",".join(final.blockers)
            )

        return BackblazeB2RoundTripResult(
            status="PASS",
            checkpoint_sha256=stored.sha256,
            generation=stored.generation,
            bytes=stored.bytes,
            restored_marker=restored_marker,
            cas_conflict_verified=True,
            remote_live_ready=final.remote_live_ready,
            blockers=final.blockers,
        )
