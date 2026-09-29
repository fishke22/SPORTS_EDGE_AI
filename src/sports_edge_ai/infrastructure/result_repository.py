from __future__ import annotations

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import EventResultRecord
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def find_canonical_event_id_by_provider_event(
    *,
    provider_slug: str,
    provider_event_id: str,
    paths: ProjectPaths,
) -> str | None:
    connection = connect_readonly(paths)
    try:
        json_path = f"$.{provider_slug}"
        row = connection.execute(
            """
            SELECT event_id
            FROM canonical_events
            WHERE json_extract_string(source_event_ids, ?) = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            [json_path, provider_event_id],
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else str(row[0])


def persist_event_results(
    records: tuple[EventResultRecord, ...],
    *,
    paths: ProjectPaths,
) -> None:
    connection = connect(paths)
    try:
        connection.execute("BEGIN")
        for record in records:
            connection.execute(
                """
                INSERT OR REPLACE INTO event_results
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    record.event_result_id,
                    record.event_id,
                    record.provider_id,
                    record.provider_event_id,
                    record.home_score,
                    record.away_score,
                    record.result_outcome,
                    record.completed,
                    record.observed_at,
                    record.provider_timestamp,
                    record.raw_source_ref,
                    record.payload_hash,
                ],
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def get_latest_event_result(
    *,
    event_id: str,
    paths: ProjectPaths | None = None,
) -> EventResultRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT event_result_id, event_id, provider_id, provider_event_id,
                   home_score, away_score, result_outcome, completed,
                   observed_at, provider_timestamp, raw_source_ref, payload_hash
            FROM event_results
            WHERE event_id = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            [event_id],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return EventResultRecord(
        event_result_id=row[0],
        event_id=row[1],
        provider_id=row[2],
        provider_event_id=row[3],
        home_score=row[4],
        away_score=row[5],
        result_outcome=row[6],
        completed=row[7],
        observed_at=row[8],
        provider_timestamp=row[9],
        raw_source_ref=row[10],
        payload_hash=row[11],
    )
