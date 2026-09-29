from __future__ import annotations

from dataclasses import dataclass

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect_readonly


@dataclass(frozen=True, slots=True)
class ProviderAccessPolicy:
    provider_id: str
    enabled: bool
    production_allowed: bool
    commercial_allowed: bool | None
    redistribution_allowed: bool | None
    automated_access_allowed: bool | None
    credential_required: bool
    source_terms_ref: str | None


def get_provider_access_policy(
    *,
    provider_id: str,
    paths: ProjectPaths | None = None,
) -> ProviderAccessPolicy:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT provider.provider_id, provider.enabled, provider.production_allowed,
                   license.commercial_allowed, license.redistribution_allowed,
                   license.automated_access_allowed, license.credential_required,
                   license.source_terms_ref
            FROM provider_registry provider
            JOIN source_license_registry license
              ON license.license_id = provider.license_id
            WHERE provider.provider_id = ?
            """,
            [provider_id],
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise ValueError(f"provider policy not found: {provider_id}")
    return ProviderAccessPolicy(
        provider_id=row[0],
        enabled=bool(row[1]),
        production_allowed=bool(row[2]),
        commercial_allowed=row[3],
        redistribution_allowed=row[4],
        automated_access_allowed=row[5],
        credential_required=bool(row[6]),
        source_terms_ref=row[7],
    )


def get_canonical_entity_id(
    *,
    provider_id: str,
    entity_kind: str,
    provider_entity_id: str,
    paths: ProjectPaths | None = None,
) -> str | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT mapping.canonical_entity_id
            FROM provider_entity_mapping mapping
            JOIN canonical_entities entity
              ON entity.entity_id = mapping.canonical_entity_id
            WHERE mapping.provider_id = ?
              AND mapping.entity_kind = ?
              AND mapping.provider_entity_id = ?
              AND entity.active = TRUE
            """,
            [provider_id, entity_kind, provider_entity_id],
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else str(row[0])
