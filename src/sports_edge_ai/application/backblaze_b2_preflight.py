from __future__ import annotations

from dataclasses import dataclass

from sports_edge_ai.application.checkpoint_backend import (
    CheckpointBackendCapabilities,
    assess_zero_cost_backend,
)

BACKBLAZE_B2_PREFLIGHT_VERSION = "backblaze-b2-zero-cost-preflight-v1"


@dataclass(frozen=True, slots=True)
class BackblazeB2ManualEvidence:
    no_payment_method_confirmed: bool = False
    zero_dollar_storage_cap_confirmed: bool = False
    zero_dollar_download_cap_confirmed: bool = False
    transaction_caps_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class BackblazeB2ProviderEvidence:
    credentials_configured: bool = False
    bucket_configured: bool = False
    bucket_private: bool = False
    lifecycle_rules_absent: bool = False
    cloud_replication_disabled: bool = False
    data_key_bucket_scoped: bool = False
    data_key_prefix_scoped: bool = False
    data_key_capabilities_minimal: bool = False
    pointer_key_capabilities_minimal: bool = False
    pointer_key_account_wide: bool = False
    keys_same_account: bool = False
    pointer_key_account_wide_required: bool = True
    provider_round_trip_verified: bool = False


@dataclass(frozen=True, slots=True)
class BackblazeB2PreflightAssessment:
    policy_version: str
    status: str
    storage_operations_allowed: bool
    remote_live_ready: bool
    blockers: tuple[str, ...]
    manual_evidence: BackblazeB2ManualEvidence
    provider_evidence: BackblazeB2ProviderEvidence
    backend_capabilities: CheckpointBackendCapabilities


def assess_backblaze_b2_preflight(
    *,
    manual: BackblazeB2ManualEvidence,
    provider: BackblazeB2ProviderEvidence,
) -> BackblazeB2PreflightAssessment:
    blockers: list[str] = []
    if not manual.no_payment_method_confirmed:
        blockers.append("NO_PAYMENT_METHOD_NOT_CONFIRMED")
    if not manual.zero_dollar_storage_cap_confirmed:
        blockers.append("ZERO_DOLLAR_STORAGE_CAP_NOT_CONFIRMED")
    if not manual.zero_dollar_download_cap_confirmed:
        blockers.append("ZERO_DOLLAR_DOWNLOAD_CAP_NOT_CONFIRMED")
    if not manual.transaction_caps_confirmed:
        blockers.append("TRANSACTION_CAPS_NOT_CONFIRMED")
    if not provider.credentials_configured:
        blockers.append("B2_CREDENTIALS_NOT_CONFIGURED")
    if not provider.bucket_configured:
        blockers.append("B2_BUCKET_NOT_CONFIGURED")
    if provider.bucket_configured and not provider.bucket_private:
        blockers.append("B2_BUCKET_NOT_PRIVATE")
    if provider.bucket_configured and not provider.lifecycle_rules_absent:
        blockers.append("B2_LIFECYCLE_RULES_PRESENT")
    if provider.bucket_configured and not provider.cloud_replication_disabled:
        blockers.append("B2_CLOUD_REPLICATION_ENABLED_OR_UNVERIFIED")
    if provider.credentials_configured and not provider.data_key_bucket_scoped:
        blockers.append("B2_DATA_KEY_NOT_BUCKET_SCOPED")
    if provider.credentials_configured and not provider.data_key_prefix_scoped:
        blockers.append("B2_DATA_KEY_NOT_PREFIX_SCOPED")
    if provider.credentials_configured and not provider.data_key_capabilities_minimal:
        blockers.append("B2_DATA_KEY_CAPABILITIES_NOT_MINIMAL")
    if provider.credentials_configured and not provider.pointer_key_capabilities_minimal:
        blockers.append("B2_POINTER_KEY_CAPABILITIES_NOT_MINIMAL")
    if provider.credentials_configured and not provider.pointer_key_account_wide:
        blockers.append("B2_POINTER_KEY_NOT_ACCOUNT_WIDE")
    if provider.credentials_configured and not provider.keys_same_account:
        blockers.append("B2_KEYS_NOT_SAME_ACCOUNT")
    if not provider.provider_round_trip_verified:
        blockers.append("B2_PROVIDER_ROUND_TRIP_NOT_VERIFIED")

    capabilities = CheckpointBackendCapabilities(
        backend_id="backblaze-b2-native-v1",
        private_storage=provider.bucket_private,
        durable_storage=True,
        automatic_billing_possible=not (
            manual.no_payment_method_confirmed
            and manual.zero_dollar_storage_cap_confirmed
            and manual.zero_dollar_download_cap_confirmed
            and manual.transaction_caps_confirmed
        ),
        atomic_publish=True,
        versioned_objects=True,
        single_writer_guard=provider.pointer_key_capabilities_minimal,
        quota_fail_closed=(
            manual.zero_dollar_storage_cap_confirmed
            and manual.zero_dollar_download_cap_confirmed
            and manual.transaction_caps_confirmed
        ),
        secret_separation=provider.credentials_configured,
        portable_export=True,
        remote_access=True,
        reference_only=False,
    )
    backend_assessment = assess_zero_cost_backend(capabilities)
    for blocker in backend_assessment.blockers:
        if blocker not in blockers:
            blockers.append(blocker)

    storage_operations_allowed = not any(
        blocker
        for blocker in blockers
        if blocker != "B2_PROVIDER_ROUND_TRIP_NOT_VERIFIED"
    )
    remote_live_ready = not blockers
    return BackblazeB2PreflightAssessment(
        policy_version=BACKBLAZE_B2_PREFLIGHT_VERSION,
        status="READY" if remote_live_ready else "LIVE_REMOTE_BLOCKED",
        storage_operations_allowed=storage_operations_allowed,
        remote_live_ready=remote_live_ready,
        blockers=tuple(blockers),
        manual_evidence=manual,
        provider_evidence=provider,
        backend_capabilities=capabilities,
    )
