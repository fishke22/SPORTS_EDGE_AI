from __future__ import annotations

from sports_edge_ai.application.backblaze_b2_preflight import (
    BackblazeB2PreflightAssessment,
    BackblazeB2ProviderEvidence,
    assess_backblaze_b2_preflight,
)
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.infrastructure.providers.backblaze_b2 import (
    B2Transport,
    BackblazeB2CheckpointBackend,
    manual_evidence_from_settings,
)


def _credential_configured(settings: Settings) -> bool:
    values = (
        settings.backblaze_b2_key_id,
        settings.backblaze_b2_application_key,
        settings.backblaze_b2_pointer_key_id,
        settings.backblaze_b2_pointer_application_key,
    )
    return all(
        value is not None and bool(value.get_secret_value().strip())
        for value in values
    )


def get_backblaze_b2_preflight_status(
    *,
    settings: Settings | None = None,
    live: bool = False,
    transport: B2Transport | None = None,
    provider_round_trip_verified: bool = False,
) -> BackblazeB2PreflightAssessment:
    effective_settings = settings or Settings()
    if live:
        return BackblazeB2CheckpointBackend(
            settings=effective_settings,
            transport=transport,
        ).preflight(
            provider_round_trip_verified=provider_round_trip_verified,
        )

    provider = BackblazeB2ProviderEvidence(
        credentials_configured=_credential_configured(effective_settings),
        bucket_configured=bool(
            (effective_settings.backblaze_b2_bucket_id or "").strip()
            and (effective_settings.backblaze_b2_bucket_name or "").strip()
        ),
        provider_round_trip_verified=provider_round_trip_verified,
    )
    return assess_backblaze_b2_preflight(
        manual=manual_evidence_from_settings(effective_settings),
        provider=provider,
    )
