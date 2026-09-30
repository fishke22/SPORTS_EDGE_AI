from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sports_edge_ai.common.root import ProjectPaths

ZERO_COST_POLICY_VERSION = "zero-cost-runtime-v1"


@dataclass(frozen=True, slots=True)
class ZeroCostRuntimeStatus:
    policy_version: str
    status: str
    paid_services_allowed: bool
    automatic_billing_allowed: bool
    public_repo_is_state_authority: bool
    github_actions_artifact_is_state_authority: bool
    remote_live_collection_ready: bool
    checkpoint_available: bool
    latest_checkpoint_relative_path: str | None
    blockers: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    safe_modes: tuple[str, ...]
    forbidden_fallbacks: tuple[str, ...]


def _latest_checkpoint(paths: ProjectPaths) -> Path | None:
    checkpoint_dir = paths.backups / "operational-checkpoints"
    if not checkpoint_dir.is_dir():
        return None
    candidates = sorted(
        path for path in checkpoint_dir.glob("operational-checkpoint-*.zip") if path.is_file()
    )
    return None if not candidates else candidates[-1]


def get_zero_cost_runtime_status(
    *,
    paths: ProjectPaths | None = None,
) -> ZeroCostRuntimeStatus:
    effective_paths = paths or ProjectPaths.discover()
    latest = _latest_checkpoint(effective_paths)
    blockers = ["NO_VERIFIED_ZERO_COST_DURABLE_BACKEND"]
    if latest is None:
        blockers.append("NO_OPERATIONAL_CHECKPOINT")

    return ZeroCostRuntimeStatus(
        policy_version=ZERO_COST_POLICY_VERSION,
        status="LIVE_REMOTE_BLOCKED",
        paid_services_allowed=False,
        automatic_billing_allowed=False,
        public_repo_is_state_authority=False,
        github_actions_artifact_is_state_authority=False,
        remote_live_collection_ready=False,
        checkpoint_available=latest is not None,
        latest_checkpoint_relative_path=(
            None if latest is None else latest.relative_to(effective_paths.root).as_posix()
        ),
        blockers=tuple(blockers),
        required_capabilities=(
            "PRIVATE_DURABLE_CHECKPOINT_STORAGE",
            "NO_AUTOMATIC_BILLING",
            "SECRET_INJECTION_OUTSIDE_CHECKPOINT",
            "SINGLE_WRITER_OR_EQUIVALENT_CONCURRENCY_GUARD",
            "ATOMIC_CHECKPOINT_REPLACEMENT",
            "QUOTA_FAILURE_MUST_STOP_REMOTE_LIVE",
        ),
        safe_modes=(
            "REPO_SMOKE",
            "LOCAL_LIVE_WHEN_HOST_ON",
            "BUILD_PRIVATE_OPERATIONAL_CHECKPOINT",
            "RESTORE_PRIVATE_CHECKPOINT_TO_EMPTY_RUNTIME",
            "PUBLIC_GITHUB_ACTIONS_FOR_EPHEMERAL_COMPUTE_ONLY",
        ),
        forbidden_fallbacks=(
            "AUTO_UPGRADE_TO_PAID",
            "PUBLIC_GIT_RUNTIME_STATE",
            "GITHUB_ACTIONS_ARTIFACT_AS_STATE_AUTHORITY",
            "DELETE_POINT_IN_TIME_EVIDENCE_TO_FIT_FREE_QUOTA",
            "EMBED_PROVIDER_SECRET_IN_CHECKPOINT",
        ),
    )
