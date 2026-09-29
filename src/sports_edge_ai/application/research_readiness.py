from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sports_edge_ai.application.local_nba_modeling import (
    LocalNBAResearchResult,
    evaluate_local_nba_dataset,
)
from sports_edge_ai.application.local_nba_research import (
    LocalNBATrainingDataset,
    build_local_nba_training_samples,
)
from sports_edge_ai.application.validation_gate import research_validation_policy
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    ResearchCycleRunRecord,
    ResearchCycleStatus,
    ResearchReadinessAssessment,
    ResearchReadinessPolicy,
    ResearchReadinessStatus,
    ResearchReadinessStatusRecord,
)
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.research_readiness_repository import (
    get_evaluated_run_for_fingerprint,
    get_latest_research_cycle_run,
    persist_research_cycle_run,
)

RESEARCH_KEY = "nba-pregame-moneyline-v1"


@dataclass(frozen=True, slots=True)
class ResearchEvaluationArtifact:
    relative_path: str
    sha256: str


def nba_research_readiness_policy() -> ResearchReadinessPolicy:
    validation = research_validation_policy()
    return ResearchReadinessPolicy(
        policy_version="nba-readiness-v1",
        research_key=RESEARCH_KEY,
        validation_policy_version=validation.policy_version,
        decision_horizon_hours=6,
        min_train_size=160,
        test_size=20,
        calibration_size=20,
        bootstrap_iterations=1000,
    )


def _require_aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _sample_payload(dataset: LocalNBATrainingDataset, count: int | None = None) -> list[object]:
    samples = dataset.samples if count is None else dataset.samples[:count]
    return [sample.model_dump(mode="json") for sample in samples]


def _fold_preflight_blockers(
    dataset: LocalNBATrainingDataset,
    policy: ResearchReadinessPolicy,
) -> tuple[str, ...]:
    samples = dataset.samples
    blockers: list[str] = []
    if policy.calibration_size and policy.min_train_size < policy.calibration_size + 2:
        return ("calibration_configuration_invalid",)

    fold_count = max(0, (len(samples) - policy.min_train_size) // policy.test_size)
    for fold_index in range(fold_count):
        test_start_index = policy.min_train_size + fold_index * policy.test_size
        fold_start = samples[test_start_index].features.decision_as_of
        train = tuple(
            sample
            for sample in samples[:test_start_index]
            if sample.result_observed_at <= fold_start
        )
        if len(train) < policy.min_train_size:
            blockers.append(f"fold_{fold_index}:settled_train_below_minimum")
            continue

        if policy.calibration_size:
            base_train = train[: -policy.calibration_size]
            calibration = train[-policy.calibration_size :]
            if len({sample.home_win for sample in base_train}) < 2:
                blockers.append(f"fold_{fold_index}:base_training_single_class")
            if len({sample.home_win for sample in calibration}) < 2:
                blockers.append(f"fold_{fold_index}:calibration_single_class")
            if (
                max(sample.result_observed_at for sample in base_train)
                > calibration[0].features.decision_as_of
            ):
                blockers.append(f"fold_{fold_index}:training_outcomes_overlap_calibration")
            if max(sample.result_observed_at for sample in calibration) > fold_start:
                blockers.append(f"fold_{fold_index}:calibration_outcomes_not_available")
        elif len({sample.home_win for sample in train}) < 2:
            blockers.append(f"fold_{fold_index}:training_single_class")

    return tuple(blockers)


def assess_nba_training_dataset_readiness(
    dataset: LocalNBATrainingDataset,
    *,
    policy: ResearchReadinessPolicy | None = None,
    checked_at: datetime | None = None,
) -> ResearchReadinessAssessment:
    effective_policy = policy or nba_research_readiness_policy()
    now = _require_aware(checked_at or datetime.now(UTC), "checked_at")
    validation = research_validation_policy()
    if validation.policy_version != effective_policy.validation_policy_version:
        raise RuntimeError("readiness policy validation version does not match validation gate")

    usable = len(dataset.samples)
    evaluation_min_usable = effective_policy.min_train_size + effective_policy.test_size
    fold_count = max(0, (usable - effective_policy.min_train_size) // effective_policy.test_size)
    evaluation_capacity = fold_count * effective_policy.test_size
    validation_blocks = math.ceil(validation.min_sample_count / effective_policy.test_size)
    validation_min_usable = (
        effective_policy.min_train_size + validation_blocks * effective_policy.test_size
    )
    consumed_sample_count = (
        effective_policy.min_train_size + evaluation_capacity if fold_count else 0
    )

    blockers: list[str] = []
    if usable < evaluation_min_usable:
        blockers.append("usable_samples_below_evaluation_minimum")
    blockers.extend(_fold_preflight_blockers(dataset, effective_policy))
    ready_for_evaluation = fold_count > 0 and not blockers
    validation_sample_ready = (
        ready_for_evaluation and evaluation_capacity >= validation.min_sample_count
    )

    if validation_sample_ready:
        readiness_status = ResearchReadinessStatus.VALIDATION_SAMPLE_READY
    elif ready_for_evaluation:
        readiness_status = ResearchReadinessStatus.EVALUATION_READY
    else:
        readiness_status = ResearchReadinessStatus.NOT_READY

    dataset_fingerprint = _sha256(
        {
            "research_key": effective_policy.research_key,
            "samples": _sample_payload(dataset),
        }
    )
    evaluation_fingerprint = None
    if ready_for_evaluation:
        evaluation_fingerprint = _sha256(
            {
                "policy": effective_policy.model_dump(mode="json"),
                "samples": _sample_payload(dataset, consumed_sample_count),
            }
        )

    decisive = dataset.decisive_event_count
    decision_coverage = None if decisive == 0 else dataset.decision_odds_covered_count / decisive
    closing_coverage = None if decisive == 0 else dataset.closing_odds_covered_count / decisive
    return ResearchReadinessAssessment(
        research_key=effective_policy.research_key,
        checked_at=now,
        readiness_policy_version=effective_policy.policy_version,
        validation_policy_version=validation.policy_version,
        readiness_status=readiness_status,
        dataset_fingerprint=dataset_fingerprint,
        evaluation_fingerprint=evaluation_fingerprint,
        candidate_event_count=dataset.candidate_event_count,
        decisive_event_count=decisive,
        usable_sample_count=usable,
        decision_odds_covered_count=dataset.decision_odds_covered_count,
        closing_odds_covered_count=dataset.closing_odds_covered_count,
        decision_odds_coverage_rate=decision_coverage,
        closing_odds_coverage_rate=closing_coverage,
        skipped_missing_odds=dataset.skipped_missing_odds,
        skipped_non_decisive_result=dataset.skipped_non_decisive_result,
        skipped_feature_error=dataset.skipped_feature_error,
        decision_horizon_hours=effective_policy.decision_horizon_hours,
        min_train_size=effective_policy.min_train_size,
        test_size=effective_policy.test_size,
        calibration_size=effective_policy.calibration_size,
        bootstrap_iterations=effective_policy.bootstrap_iterations,
        evaluation_min_usable_samples=evaluation_min_usable,
        evaluation_sample_capacity=evaluation_capacity,
        validation_min_evaluation_samples=validation.min_sample_count,
        validation_min_usable_samples=validation_min_usable,
        remaining_to_evaluation=max(0, evaluation_min_usable - usable),
        remaining_to_validation_samples=max(0, validation_min_usable - usable),
        fold_count_capacity=fold_count,
        ready_for_evaluation=ready_for_evaluation,
        validation_sample_ready=validation_sample_ready,
        blockers=tuple(blockers),
    )


def _assessment_and_dataset(
    *,
    paths: ProjectPaths,
    policy: ResearchReadinessPolicy,
    checked_at: datetime,
) -> tuple[ResearchReadinessAssessment, LocalNBATrainingDataset]:
    dataset = build_local_nba_training_samples(
        paths=paths,
        decision_horizon_hours=policy.decision_horizon_hours,
    )
    return (
        assess_nba_training_dataset_readiness(
            dataset,
            policy=policy,
            checked_at=checked_at,
        ),
        dataset,
    )


def _assessment_from_cycle_run(
    record: ResearchCycleRunRecord,
) -> ResearchReadinessAssessment:
    if record.validation_sample_ready:
        readiness_status = ResearchReadinessStatus.VALIDATION_SAMPLE_READY
    elif record.ready_for_evaluation:
        readiness_status = ResearchReadinessStatus.EVALUATION_READY
    else:
        readiness_status = ResearchReadinessStatus.NOT_READY

    decisive = record.decisive_event_count
    return ResearchReadinessAssessment(
        research_key=record.research_key,
        checked_at=record.checked_at,
        readiness_policy_version=record.readiness_policy_version,
        validation_policy_version=record.validation_policy_version,
        readiness_status=readiness_status,
        dataset_fingerprint=record.dataset_fingerprint,
        evaluation_fingerprint=record.evaluation_fingerprint,
        candidate_event_count=record.candidate_event_count,
        decisive_event_count=decisive,
        usable_sample_count=record.usable_sample_count,
        decision_odds_covered_count=record.decision_odds_covered_count,
        closing_odds_covered_count=record.closing_odds_covered_count,
        decision_odds_coverage_rate=(
            None if decisive == 0 else record.decision_odds_covered_count / decisive
        ),
        closing_odds_coverage_rate=(
            None if decisive == 0 else record.closing_odds_covered_count / decisive
        ),
        skipped_missing_odds=record.skipped_missing_odds,
        skipped_non_decisive_result=record.skipped_non_decisive_result,
        skipped_feature_error=record.skipped_feature_error,
        decision_horizon_hours=record.decision_horizon_hours,
        min_train_size=record.min_train_size,
        test_size=record.test_size,
        calibration_size=record.calibration_size,
        bootstrap_iterations=record.bootstrap_iterations,
        evaluation_min_usable_samples=record.evaluation_min_usable_samples,
        evaluation_sample_capacity=record.evaluation_sample_capacity,
        validation_min_evaluation_samples=record.validation_min_evaluation_samples,
        validation_min_usable_samples=record.validation_min_usable_samples,
        remaining_to_evaluation=record.remaining_to_evaluation,
        remaining_to_validation_samples=record.remaining_to_validation_samples,
        fold_count_capacity=record.fold_count_capacity,
        ready_for_evaluation=record.ready_for_evaluation,
        validation_sample_ready=record.validation_sample_ready,
        blockers=record.blockers,
    )


def get_nba_research_readiness_status(
    *,
    paths: ProjectPaths | None = None,
    checked_at: datetime | None = None,
    policy: ResearchReadinessPolicy | None = None,
    refresh: bool = True,
) -> ResearchReadinessStatusRecord:
    effective_paths = paths or ProjectPaths.discover()
    effective_policy = policy or nba_research_readiness_policy()
    latest = get_latest_research_cycle_run(
        research_key=effective_policy.research_key,
        paths=effective_paths,
    )
    if not refresh and latest is not None:
        return ResearchReadinessStatusRecord(
            assessment=_assessment_from_cycle_run(latest),
            latest_run=latest,
        )

    now = _require_aware(checked_at or datetime.now(UTC), "checked_at")
    assessment, _ = _assessment_and_dataset(
        paths=effective_paths,
        policy=effective_policy,
        checked_at=now,
    )
    return ResearchReadinessStatusRecord(assessment=assessment, latest_run=latest)


def _record_from_assessment(
    assessment: ResearchReadinessAssessment,
    *,
    trigger_kind: str,
    status: ResearchCycleStatus,
    evaluation_sample_count: int | None = None,
    validation_passed: bool | None = None,
    report_relative_path: str | None = None,
    error_summary: str | None = None,
) -> ResearchCycleRunRecord:
    return ResearchCycleRunRecord(
        research_run_id=uuid4().hex,
        research_key=assessment.research_key,
        readiness_policy_version=assessment.readiness_policy_version,
        validation_policy_version=assessment.validation_policy_version,
        trigger_kind=trigger_kind,
        checked_at=assessment.checked_at,
        status=status,
        dataset_fingerprint=assessment.dataset_fingerprint,
        evaluation_fingerprint=assessment.evaluation_fingerprint,
        decision_horizon_hours=assessment.decision_horizon_hours,
        min_train_size=assessment.min_train_size,
        test_size=assessment.test_size,
        calibration_size=assessment.calibration_size,
        bootstrap_iterations=assessment.bootstrap_iterations,
        candidate_event_count=assessment.candidate_event_count,
        decisive_event_count=assessment.decisive_event_count,
        usable_sample_count=assessment.usable_sample_count,
        decision_odds_covered_count=assessment.decision_odds_covered_count,
        closing_odds_covered_count=assessment.closing_odds_covered_count,
        skipped_missing_odds=assessment.skipped_missing_odds,
        skipped_non_decisive_result=assessment.skipped_non_decisive_result,
        skipped_feature_error=assessment.skipped_feature_error,
        evaluation_min_usable_samples=assessment.evaluation_min_usable_samples,
        evaluation_sample_capacity=assessment.evaluation_sample_capacity,
        validation_min_evaluation_samples=assessment.validation_min_evaluation_samples,
        validation_min_usable_samples=assessment.validation_min_usable_samples,
        remaining_to_evaluation=assessment.remaining_to_evaluation,
        remaining_to_validation_samples=assessment.remaining_to_validation_samples,
        fold_count_capacity=assessment.fold_count_capacity,
        ready_for_evaluation=assessment.ready_for_evaluation,
        validation_sample_ready=assessment.validation_sample_ready,
        blockers=assessment.blockers,
        evaluation_sample_count=evaluation_sample_count,
        validation_passed=validation_passed,
        report_relative_path=report_relative_path,
        model_promotion_performed=False,
        error_summary=error_summary,
    )


def _persist_research_evaluation_report(
    *,
    assessment: ResearchReadinessAssessment,
    result: LocalNBAResearchResult,
    paths: ProjectPaths,
) -> ResearchEvaluationArtifact:
    if result.evaluation is None or result.validation is None:
        raise RuntimeError("research evaluation report requires evaluation and validation evidence")
    payload: dict[str, object] = {
        "schema_version": "research-backtest-report-v1",
        "research_key": assessment.research_key,
        "readiness": assessment.model_dump(mode="json", exclude={"checked_at"}),
        "evaluation": result.evaluation.model_dump(mode="json"),
        "validation_gate": result.validation.model_dump(mode="json"),
        "model_promotion_performed": False,
    }
    report_json = _canonical_json(payload)
    sha256 = hashlib.sha256(report_json.encode("utf-8")).hexdigest()
    output_dir = paths.reports / "backtests" / "readiness"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sha256}.json"
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") != report_json:
            raise RuntimeError("existing research report differs from checksum path")
    else:
        output_path.write_text(report_json, encoding="utf-8")
    return ResearchEvaluationArtifact(
        relative_path=output_path.relative_to(paths.root).as_posix(),
        sha256=sha256,
    )


def run_nba_research_cycle(
    *,
    paths: ProjectPaths | None = None,
    checked_at: datetime | None = None,
    policy: ResearchReadinessPolicy | None = None,
    trigger_kind: str = "MANUAL",
) -> ResearchCycleRunRecord:
    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    effective_policy = policy or nba_research_readiness_policy()
    now = _require_aware(checked_at or datetime.now(UTC), "checked_at")
    assessment, dataset = _assessment_and_dataset(
        paths=effective_paths,
        policy=effective_policy,
        checked_at=now,
    )

    if not assessment.ready_for_evaluation:
        record = _record_from_assessment(
            assessment,
            trigger_kind=trigger_kind,
            status=ResearchCycleStatus.NOT_READY,
        )
        persist_research_cycle_run(record, paths=effective_paths)
        return record

    if assessment.evaluation_fingerprint is None:
        raise RuntimeError("ready assessment is missing evaluation fingerprint")
    existing = get_evaluated_run_for_fingerprint(
        research_key=assessment.research_key,
        evaluation_fingerprint=assessment.evaluation_fingerprint,
        paths=effective_paths,
    )
    if existing is not None:
        record = _record_from_assessment(
            assessment,
            trigger_kind=trigger_kind,
            status=ResearchCycleStatus.SKIPPED_UNCHANGED,
            evaluation_sample_count=existing.evaluation_sample_count,
            validation_passed=existing.validation_passed,
            report_relative_path=existing.report_relative_path,
        )
        persist_research_cycle_run(record, paths=effective_paths)
        return record

    try:
        result = evaluate_local_nba_dataset(
            dataset,
            paths=effective_paths,
            min_train_size=effective_policy.min_train_size,
            test_size=effective_policy.test_size,
            calibration_size=effective_policy.calibration_size,
            bootstrap_iterations=effective_policy.bootstrap_iterations,
        )
        if result.evaluation is None or result.validation is None:
            raise RuntimeError("ready research cycle produced no evaluation evidence")
        artifact = _persist_research_evaluation_report(
            assessment=assessment,
            result=result,
            paths=effective_paths,
        )
        status = (
            ResearchCycleStatus.EVALUATED_GATE_PASSED
            if result.validation.is_model_validated
            else ResearchCycleStatus.EVALUATED_NOT_VALIDATED
        )
        record = _record_from_assessment(
            assessment,
            trigger_kind=trigger_kind,
            status=status,
            evaluation_sample_count=result.evaluation.sample_count,
            validation_passed=result.validation.is_model_validated,
            report_relative_path=artifact.relative_path,
        )
        persist_research_cycle_run(record, paths=effective_paths)
        return record
    except Exception as exc:
        failed = _record_from_assessment(
            assessment,
            trigger_kind=trigger_kind,
            status=ResearchCycleStatus.FAILED,
            error_summary=f"{type(exc).__name__}: {exc}"[:500],
        )
        persist_research_cycle_run(failed, paths=effective_paths)
        raise
