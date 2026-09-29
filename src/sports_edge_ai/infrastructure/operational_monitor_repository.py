from __future__ import annotations

import json
from typing import Any

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    OperationalMonitorSnapshotRecord,
    OperationalSeverity,
    ResearchReadinessStatus,
)
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def persist_operational_monitor_snapshot(
    record: OperationalMonitorSnapshotRecord,
    *,
    paths: ProjectPaths,
) -> None:
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT INTO operational_monitor_snapshots VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.monitor_id,
                record.policy_version,
                record.trigger_kind,
                record.checked_at,
                record.severity.value,
                record.collection_run_id,
                record.collection_run_status,
                record.collection_age_minutes,
                record.research_run_id,
                record.research_run_status,
                record.research_age_minutes,
                record.requests_used,
                record.requests_remaining,
                record.local_monthly_budget,
                record.budget_usage_ratio,
                record.live_event_count,
                record.odds_snapshot_count,
                record.completed_result_count,
                record.past_event_without_result_count,
                record.readiness_status.value,
                record.usable_sample_count,
                record.remaining_to_evaluation,
                record.remaining_to_validation_samples,
                record.decision_odds_coverage_rate,
                record.closing_odds_coverage_rate,
                record.odds_snapshot_delta,
                record.completed_result_delta,
                record.usable_sample_delta,
                json.dumps(record.alerts, sort_keys=True),
            ],
        )
    finally:
        connection.close()


def _row_to_record(row: tuple[Any, ...]) -> OperationalMonitorSnapshotRecord:
    alerts_raw = row[28]
    alerts = json.loads(alerts_raw) if isinstance(alerts_raw, str) else alerts_raw
    return OperationalMonitorSnapshotRecord(
        monitor_id=str(row[0]),
        policy_version=str(row[1]),
        trigger_kind=str(row[2]),
        checked_at=row[3],
        severity=OperationalSeverity(str(row[4])),
        collection_run_id=None if row[5] is None else str(row[5]),
        collection_run_status=None if row[6] is None else str(row[6]),
        collection_age_minutes=None if row[7] is None else float(row[7]),
        research_run_id=None if row[8] is None else str(row[8]),
        research_run_status=None if row[9] is None else str(row[9]),
        research_age_minutes=None if row[10] is None else float(row[10]),
        requests_used=None if row[11] is None else int(row[11]),
        requests_remaining=None if row[12] is None else int(row[12]),
        local_monthly_budget=None if row[13] is None else int(row[13]),
        budget_usage_ratio=None if row[14] is None else float(row[14]),
        live_event_count=int(row[15]),
        odds_snapshot_count=int(row[16]),
        completed_result_count=int(row[17]),
        past_event_without_result_count=int(row[18]),
        readiness_status=ResearchReadinessStatus(str(row[19])),
        usable_sample_count=int(row[20]),
        remaining_to_evaluation=int(row[21]),
        remaining_to_validation_samples=int(row[22]),
        decision_odds_coverage_rate=None if row[23] is None else float(row[23]),
        closing_odds_coverage_rate=None if row[24] is None else float(row[24]),
        odds_snapshot_delta=None if row[25] is None else int(row[25]),
        completed_result_delta=None if row[26] is None else int(row[26]),
        usable_sample_delta=None if row[27] is None else int(row[27]),
        alerts=tuple(str(item) for item in alerts),
    )


_SELECT = """
SELECT monitor_id, policy_version, trigger_kind, checked_at, severity,
       collection_run_id, collection_run_status, collection_age_minutes,
       research_run_id, research_run_status, research_age_minutes,
       requests_used, requests_remaining, local_monthly_budget, budget_usage_ratio,
       live_event_count, odds_snapshot_count, completed_result_count,
       past_event_without_result_count, readiness_status, usable_sample_count,
       remaining_to_evaluation, remaining_to_validation_samples,
       decision_odds_coverage_rate, closing_odds_coverage_rate,
       odds_snapshot_delta, completed_result_delta, usable_sample_delta, alerts_json
FROM operational_monitor_snapshots
"""
def get_latest_operational_monitor_snapshot(
    *,
    paths: ProjectPaths | None = None,
) -> OperationalMonitorSnapshotRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            _SELECT
            + """
            ORDER BY checked_at DESC, monitor_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else _row_to_record(row)
