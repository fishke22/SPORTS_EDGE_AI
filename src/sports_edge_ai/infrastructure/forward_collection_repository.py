from __future__ import annotations

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import DataQualityStatus, ForwardCollectionRunRecord
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def persist_forward_collection_run(
    record: ForwardCollectionRunRecord,
    *,
    paths: ProjectPaths,
) -> None:
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT INTO forward_collection_runs VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.collection_run_id,
                record.provider_id,
                record.trigger_kind,
                record.started_at,
                record.finished_at,
                record.status,
                record.current_due,
                record.scores_due,
                record.current_attempted,
                record.scores_attempted,
                record.events_count,
                record.odds_count,
                record.results_count,
                record.unresolved_count,
                None if record.data_quality_status is None else record.data_quality_status.value,
                record.mapping_rate,
                record.requests_used_before,
                record.requests_used_after,
                record.credits_spent,
                record.requests_remaining_after,
                record.error_summary,
            ],
        )
    finally:
        connection.close()


def get_latest_forward_collection_run(
    *,
    provider_id: str,
    paths: ProjectPaths | None = None,
) -> ForwardCollectionRunRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT collection_run_id, provider_id, trigger_kind, started_at, finished_at,
                   status, current_due, scores_due, current_attempted, scores_attempted,
                   events_count, odds_count, results_count, unresolved_count,
                   data_quality_status, mapping_rate, requests_used_before,
                   requests_used_after, credits_spent, requests_remaining_after,
                   error_summary
            FROM forward_collection_runs
            WHERE provider_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            [provider_id],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return ForwardCollectionRunRecord(
        collection_run_id=row[0],
        provider_id=row[1],
        trigger_kind=row[2],
        started_at=row[3],
        finished_at=row[4],
        status=row[5],
        current_due=row[6],
        scores_due=row[7],
        current_attempted=row[8],
        scores_attempted=row[9],
        events_count=row[10],
        odds_count=row[11],
        results_count=row[12],
        unresolved_count=row[13],
        data_quality_status=None if row[14] is None else DataQualityStatus(row[14]),
        mapping_rate=row[15],
        requests_used_before=row[16],
        requests_used_after=row[17],
        credits_spent=row[18],
        requests_remaining_after=row[19],
        error_summary=row[20],
    )
