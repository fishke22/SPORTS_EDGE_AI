from __future__ import annotations

from pathlib import Path

from sports_edge_ai.application.zero_cost_runtime import get_zero_cost_runtime_status
from sports_edge_ai.common.root import ProjectPaths


def test_zero_cost_policy_is_hard_fail_closed_without_private_durable_backend(
    tmp_path: Path,
) -> None:
    paths = ProjectPaths(tmp_path)
    paths.ensure_runtime_dirs()

    status = get_zero_cost_runtime_status(paths=paths)

    assert status.status == "LIVE_REMOTE_BLOCKED"
    assert status.paid_services_allowed is False
    assert status.automatic_billing_allowed is False
    assert status.public_repo_is_state_authority is False
    assert status.github_actions_artifact_is_state_authority is False
    assert status.remote_live_collection_ready is False
    assert "NO_VERIFIED_ZERO_COST_DURABLE_BACKEND" in status.blockers
    assert "NO_OPERATIONAL_CHECKPOINT" in status.blockers
    assert "PRIVATE_DURABLE_CHECKPOINT_STORAGE" in status.required_capabilities
    assert "QUOTA_FAILURE_MUST_STOP_REMOTE_LIVE" in status.required_capabilities
    assert "PUBLIC_GITHUB_ACTIONS_FOR_EPHEMERAL_COMPUTE_ONLY" in status.safe_modes
    assert "AUTO_UPGRADE_TO_PAID" in status.forbidden_fallbacks
    assert "GITHUB_ACTIONS_ARTIFACT_AS_STATE_AUTHORITY" in status.forbidden_fallbacks
    assert "DELETE_POINT_IN_TIME_EVIDENCE_TO_FIT_FREE_QUOTA" in status.forbidden_fallbacks
