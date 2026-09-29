from __future__ import annotations

import json
from typing import Any

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    ResearchCycleRunRecord,
    ResearchCycleStatus,
)
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def persist_research_cycle_run(
    record: ResearchCycleRunRecord,
    *,
    paths: ProjectPaths,
) -> None:
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT INTO research_readiness_runs VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.research_run_id,
                record.research_key,
                record.readiness_policy_version,
                record.validation_policy_version,
                record.trigger_kind,
                record.checked_at,
                record.status.value,
                record.dataset_fingerprint,
                record.evaluation_fingerprint,
                record.decision_horizon_hours,
                record.min_train_size,
                record.test_size,
                record.calibration_size,
                record.bootstrap_iterations,
                record.candidate_event_count,
                record.decisive_event_count,
                record.usable_sample_count,
                record.decision_odds_covered_count,
                record.closing_odds_covered_count,
                record.skipped_missing_odds,
                record.skipped_non_decisive_result,
                record.skipped_feature_error,
                record.evaluation_min_usable_samples,
                record.evaluation_sample_capacity,
                record.validation_min_evaluation_samples,
                record.validation_min_usable_samples,
                record.remaining_to_evaluation,
                record.remaining_to_validation_samples,
                record.fold_count_capacity,
                record.ready_for_evaluation,
                record.validation_sample_ready,
                json.dumps(record.blockers, sort_keys=True),
                record.evaluation_sample_count,
                record.validation_passed,
                record.report_relative_path,
                record.model_promotion_performed,
                record.error_summary,
            ],
        )
    finally:
        connection.close()


def _row_to_record(row: tuple[Any, ...]) -> ResearchCycleRunRecord:
    blockers_raw = row[31]
    blockers = json.loads(blockers_raw) if isinstance(blockers_raw, str) else blockers_raw
    return ResearchCycleRunRecord(
        research_run_id=str(row[0]),
        research_key=str(row[1]),
        readiness_policy_version=str(row[2]),
        validation_policy_version=str(row[3]),
        trigger_kind=str(row[4]),
        checked_at=row[5],
        status=ResearchCycleStatus(str(row[6])),
        dataset_fingerprint=str(row[7]),
        evaluation_fingerprint=None if row[8] is None else str(row[8]),
        decision_horizon_hours=int(row[9]),
        min_train_size=int(row[10]),
        test_size=int(row[11]),
        calibration_size=int(row[12]),
        bootstrap_iterations=int(row[13]),
        candidate_event_count=int(row[14]),
        decisive_event_count=int(row[15]),
        usable_sample_count=int(row[16]),
        decision_odds_covered_count=int(row[17]),
        closing_odds_covered_count=int(row[18]),
        skipped_missing_odds=int(row[19]),
        skipped_non_decisive_result=int(row[20]),
        skipped_feature_error=int(row[21]),
        evaluation_min_usable_samples=int(row[22]),
        evaluation_sample_capacity=int(row[23]),
        validation_min_evaluation_samples=int(row[24]),
        validation_min_usable_samples=int(row[25]),
        remaining_to_evaluation=int(row[26]),
        remaining_to_validation_samples=int(row[27]),
        fold_count_capacity=int(row[28]),
        ready_for_evaluation=bool(row[29]),
        validation_sample_ready=bool(row[30]),
        blockers=tuple(str(item) for item in blockers),
        evaluation_sample_count=None if row[32] is None else int(row[32]),
        validation_passed=None if row[33] is None else bool(row[33]),
        report_relative_path=None if row[34] is None else str(row[34]),
        model_promotion_performed=bool(row[35]),
        error_summary=None if row[36] is None else str(row[36]),
    )


_SELECT = """
SELECT research_run_id, research_key, readiness_policy_version,
       validation_policy_version, trigger_kind, checked_at, status,
       dataset_fingerprint, evaluation_fingerprint, decision_horizon_hours,
       min_train_size, test_size, calibration_size, bootstrap_iterations,
       candidate_event_count, decisive_event_count, usable_sample_count,
       decision_odds_covered_count, closing_odds_covered_count,
       skipped_missing_odds, skipped_non_decisive_result, skipped_feature_error,
       evaluation_min_usable_samples, evaluation_sample_capacity,
       validation_min_evaluation_samples, validation_min_usable_samples,
       remaining_to_evaluation, remaining_to_validation_samples,
       fold_count_capacity, ready_for_evaluation, validation_sample_ready,
       blockers_json, evaluation_sample_count, validation_passed,
       report_relative_path, model_promotion_performed, error_summary
FROM research_readiness_runs
"""


def get_latest_research_cycle_run(
    *,
    research_key: str,
    paths: ProjectPaths | None = None,
) -> ResearchCycleRunRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            _SELECT
            + """
            WHERE research_key = ?
            ORDER BY checked_at DESC, research_run_id DESC
            LIMIT 1
            """,
            [research_key],
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else _row_to_record(row)


def get_evaluated_run_for_fingerprint(
    *,
    research_key: str,
    evaluation_fingerprint: str,
    paths: ProjectPaths | None = None,
) -> ResearchCycleRunRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            _SELECT
            + """
            WHERE research_key = ?
              AND evaluation_fingerprint = ?
              AND status IN ('EVALUATED_NOT_VALIDATED', 'EVALUATED_GATE_PASSED')
            ORDER BY checked_at DESC, research_run_id DESC
            LIMIT 1
            """,
            [research_key, evaluation_fingerprint],
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else _row_to_record(row)
