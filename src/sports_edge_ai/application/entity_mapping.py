from __future__ import annotations

from datetime import UTC, datetime

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    CanonicalEntityRecord,
    ProviderEntityProposalRecord,
    ProviderMappingReviewSummary,
)
from sports_edge_ai.infrastructure.db import connect, connect_readonly, migrate


def create_or_update_entity_proposal(
    *,
    provider_id: str,
    entity_kind: str,
    provider_entity_id: str,
    provider_display_name: str,
    provider_object_id: str | None,
    observed_at: datetime,
    paths: ProjectPaths,
) -> ProviderEntityProposalRecord:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    migrate(paths)
    connection = connect(paths)
    try:
        exact = connection.execute(
            """
            SELECT entity_id
            FROM canonical_entities
            WHERE entity_kind = ?
              AND canonical_name = ?
              AND active = TRUE
            ORDER BY entity_id
            """,
            [entity_kind, provider_display_name],
        ).fetchall()
        candidate = str(exact[0][0]) if len(exact) == 1 else None
        method = "EXACT_NAME_CANDIDATE" if candidate else "MANUAL_REVIEW_REQUIRED"
        existing = connection.execute(
            """
            SELECT status, proposed_canonical_entity_id, reviewed_at, review_note
            FROM provider_entity_proposals
            WHERE provider_id = ? AND entity_kind = ? AND provider_entity_id = ?
            """,
            [provider_id, entity_kind, provider_entity_id],
        ).fetchone()
        if existing is not None and existing[0] in {"APPROVED", "REJECTED"}:
            return ProviderEntityProposalRecord(
                provider_id=provider_id,
                entity_kind=entity_kind,
                provider_entity_id=provider_entity_id,
                provider_display_name=provider_display_name,
                provider_object_id=provider_object_id,
                proposed_canonical_entity_id=existing[1],
                proposal_method=method,
                status=existing[0],
                observed_at=observed_at,
                reviewed_at=existing[2],
                review_note=existing[3],
            )
        record = ProviderEntityProposalRecord(
            provider_id=provider_id,
            entity_kind=entity_kind,
            provider_entity_id=provider_entity_id,
            provider_display_name=provider_display_name,
            provider_object_id=provider_object_id,
            proposed_canonical_entity_id=candidate,
            proposal_method=method,
            status="PENDING",
            observed_at=observed_at,
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO provider_entity_proposals
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.provider_id,
                record.entity_kind,
                record.provider_entity_id,
                record.provider_display_name,
                record.provider_object_id,
                record.proposed_canonical_entity_id,
                record.proposal_method,
                record.status,
                record.observed_at,
                record.reviewed_at,
                record.review_note,
            ],
        )
        return record
    finally:
        connection.close()


def list_entity_proposals(
    *,
    provider_id: str,
    status: str | None = None,
    paths: ProjectPaths | None = None,
) -> tuple[ProviderEntityProposalRecord, ...]:
    connection = connect_readonly(paths)
    try:
        params: list[object] = [provider_id]
        where = "WHERE provider_id = ?"
        if status is not None:
            where += " AND status = ?"
            params.append(status)
        rows = connection.execute(
            f"""
            SELECT provider_id, entity_kind, provider_entity_id,
                   provider_display_name, provider_object_id,
                   proposed_canonical_entity_id, proposal_method, status,
                   observed_at, reviewed_at, review_note
            FROM provider_entity_proposals
            {where}
            ORDER BY entity_kind, provider_display_name
            """,
            params,
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        ProviderEntityProposalRecord(
            provider_id=row[0],
            entity_kind=row[1],
            provider_entity_id=row[2],
            provider_display_name=row[3],
            provider_object_id=row[4],
            proposed_canonical_entity_id=row[5],
            proposal_method=row[6],
            status=row[7],
            observed_at=row[8],
            reviewed_at=row[9],
            review_note=row[10],
        )
        for row in rows
    )


def list_canonical_entities(
    *,
    entity_kind: str,
    sport: str | None = None,
    entity_id_prefix: str | None = None,
    paths: ProjectPaths | None = None,
) -> tuple[CanonicalEntityRecord, ...]:
    connection = connect_readonly(paths)
    try:
        params: list[object] = [entity_kind]
        where = "WHERE entity_kind = ? AND active = TRUE"
        if sport is not None:
            where += " AND sport = ?"
            params.append(sport)
        if entity_id_prefix is not None:
            if not entity_id_prefix:
                raise ValueError("entity_id_prefix must not be empty")
            where += " AND entity_id LIKE ?"
            params.append(f"{entity_id_prefix}%")
        rows = connection.execute(
            f"""
            SELECT entity_id, entity_kind, sport, canonical_name, active, created_at
            FROM canonical_entities
            {where}
            ORDER BY canonical_name
            """,
            params,
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        CanonicalEntityRecord(
            entity_id=row[0],
            entity_kind=row[1],
            sport=row[2],
            canonical_name=row[3],
            active=bool(row[4]),
            created_at=row[5],
        )
        for row in rows
    )


def reject_entity_mapping(
    *,
    provider_id: str,
    entity_kind: str,
    provider_entity_id: str,
    review_note: str,
    paths: ProjectPaths | None = None,
) -> ProviderEntityProposalRecord:
    if not review_note.strip():
        raise ValueError("review_note is required when rejecting a mapping proposal")
    effective_paths = paths or ProjectPaths.discover()
    reviewed_at = datetime.now(UTC)
    connection = connect(effective_paths)
    try:
        proposal = connection.execute(
            """
            SELECT provider_display_name, provider_object_id, observed_at,
                   proposal_method, proposed_canonical_entity_id
            FROM provider_entity_proposals
            WHERE provider_id = ? AND entity_kind = ? AND provider_entity_id = ?
            """,
            [provider_id, entity_kind, provider_entity_id],
        ).fetchone()
        if proposal is None:
            raise ValueError("entity proposal not found")
        connection.execute("BEGIN")
        connection.execute(
            """
            DELETE FROM provider_entity_mapping
            WHERE provider_id = ? AND entity_kind = ? AND provider_entity_id = ?
            """,
            [provider_id, entity_kind, provider_entity_id],
        )
        connection.execute(
            """
            UPDATE provider_entity_proposals
            SET status = 'REJECTED', reviewed_at = ?, review_note = ?
            WHERE provider_id = ? AND entity_kind = ? AND provider_entity_id = ?
            """,
            [
                reviewed_at,
                review_note.strip(),
                provider_id,
                entity_kind,
                provider_entity_id,
            ],
        )
        connection.execute("COMMIT")
        return ProviderEntityProposalRecord(
            provider_id=provider_id,
            entity_kind=entity_kind,
            provider_entity_id=provider_entity_id,
            provider_display_name=proposal[0],
            provider_object_id=proposal[1],
            proposed_canonical_entity_id=proposal[4],
            proposal_method=proposal[3],
            status="REJECTED",
            observed_at=proposal[2],
            reviewed_at=reviewed_at,
            review_note=review_note.strip(),
        )
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()


def get_mapping_review_summary(
    *,
    provider_id: str,
    entity_kind: str,
    paths: ProjectPaths | None = None,
) -> ProviderMappingReviewSummary:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT count(*) AS proposal_count,
                   count(*) FILTER (WHERE status = 'PENDING') AS pending_count,
                   count(*) FILTER (WHERE status = 'APPROVED') AS approved_count,
                   count(*) FILTER (WHERE status = 'REJECTED') AS rejected_count
            FROM provider_entity_proposals
            WHERE provider_id = ? AND entity_kind = ?
            """,
            [provider_id, entity_kind],
        ).fetchone()
        mapping_row = connection.execute(
            """
            SELECT count(*)
            FROM provider_entity_mapping
            WHERE provider_id = ? AND entity_kind = ?
            """,
            [provider_id, entity_kind],
        ).fetchone()
    finally:
        connection.close()

    proposal_count = int(row[0]) if row is not None else 0
    pending_count = int(row[1]) if row is not None else 0
    approved_count = int(row[2]) if row is not None else 0
    rejected_count = int(row[3]) if row is not None else 0
    mapping_count = int(mapping_row[0]) if mapping_row is not None else 0
    reviewed = approved_count + rejected_count
    completion = 1.0 if proposal_count == 0 else reviewed / proposal_count
    return ProviderMappingReviewSummary(
        provider_id=provider_id,
        entity_kind=entity_kind,
        proposal_count=proposal_count,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        approved_mapping_count=mapping_count,
        review_completion_rate=completion,
    )


def approve_entity_mapping(
    *,
    provider_id: str,
    entity_kind: str,
    provider_entity_id: str,
    canonical_entity_id: str,
    review_note: str | None = None,
    paths: ProjectPaths | None = None,
) -> ProviderEntityProposalRecord:
    effective_paths = paths or ProjectPaths.discover()
    reviewed_at = datetime.now(UTC)
    connection = connect(effective_paths)
    try:
        proposal = connection.execute(
            """
            SELECT provider_display_name, provider_object_id, observed_at, proposal_method
            FROM provider_entity_proposals
            WHERE provider_id = ? AND entity_kind = ? AND provider_entity_id = ?
            """,
            [provider_id, entity_kind, provider_entity_id],
        ).fetchone()
        if proposal is None:
            raise ValueError("entity proposal not found")
        entity = connection.execute(
            """
            SELECT entity_id FROM canonical_entities
            WHERE entity_id = ? AND entity_kind = ? AND active = TRUE
            """,
            [canonical_entity_id, entity_kind],
        ).fetchone()
        if entity is None:
            raise ValueError("canonical entity not found or inactive")
        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT OR REPLACE INTO provider_entity_mapping
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                provider_id,
                entity_kind,
                provider_entity_id,
                canonical_entity_id,
                reviewed_at,
                1.0,
                "MANUAL_APPROVAL",
            ],
        )
        connection.execute(
            """
            UPDATE provider_entity_proposals
            SET proposed_canonical_entity_id = ?, status = 'APPROVED',
                reviewed_at = ?, review_note = ?
            WHERE provider_id = ? AND entity_kind = ? AND provider_entity_id = ?
            """,
            [
                canonical_entity_id,
                reviewed_at,
                review_note,
                provider_id,
                entity_kind,
                provider_entity_id,
            ],
        )
        connection.execute("COMMIT")
        return ProviderEntityProposalRecord(
            provider_id=provider_id,
            entity_kind=entity_kind,
            provider_entity_id=provider_entity_id,
            provider_display_name=proposal[0],
            provider_object_id=proposal[1],
            proposed_canonical_entity_id=canonical_entity_id,
            proposal_method=proposal[3],
            status="APPROVED",
            observed_at=proposal[2],
            reviewed_at=reviewed_at,
            review_note=review_note,
        )
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()
