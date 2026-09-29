from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sports_edge_ai.application.forward_collection import get_forward_collection_status
from sports_edge_ai.application.research_readiness import get_nba_research_readiness_status
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.domain.schemas import (
    ForwardCollectionStatusRecord,
    OperationalMonitoringPolicy,
    OperationalMonitorSnapshotRecord,
    OperationalSeverity,
    ProviderUsageSnapshot,
    ResearchReadinessStatusRecord,
)
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.operational_monitor_repository import (
    get_latest_operational_monitor_snapshot,
    persist_operational_monitor_snapshot,
)
from sports_edge_ai.infrastructure.provider_usage_repository import get_latest_provider_usage
from sports_edge_ai.infrastructure.providers.the_odds_api import PROVIDER_ID


def operational_monitoring_policy(settings: Settings) -> OperationalMonitoringPolicy:
    return OperationalMonitoringPolicy(
        policy_version="operational-monitor-v1",
        collection_stale_after_minutes=settings.operational_collection_stale_after_minutes,
        research_stale_after_minutes=settings.operational_research_stale_after_minutes,
        budget_warning_fraction=settings.operational_budget_warning_fraction,
    )
def _age_minutes(checked_at: datetime, observed_at: datetime | None) -> float | None:
    if observed_at is None:
        return None
    return max(0.0, (checked_at - observed_at).total_seconds() / 60.0)


def assess_operational_health(
    *,
    collection: ForwardCollectionStatusRecord,
    research: ResearchReadinessStatusRecord,
    usage: ProviderUsageSnapshot | None,
    previous: OperationalMonitorSnapshotRecord | None,
    policy: OperationalMonitoringPolicy,
    checked_at: datetime,
    trigger_kind: str,
    monitor_id: str | None = None,
) -> OperationalMonitorSnapshotRecord:
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("checked_at must be timezone-aware")

    warnings: list[str] = []
    failures: list[str] = []
    collection_run = collection.latest_run
    research_run = research.latest_run
    collection_age = _age_minutes(
        checked_at,
        None if collection_run is None else collection_run.finished_at,
    )
    research_age = _age_minutes(
        checked_at,
        None if research_run is None else research_run.checked_at,
    )

    if collection_run is None:
        warnings.append("collection_heartbeat_missing")
    else:
        if collection_run.status in {"FAILED", "PARTIAL"}:
            failures.append(f"collection_{collection_run.status.lower()}")
        elif collection_run.status == "DEGRADED":
            warnings.append("collection_degraded")
        if collection_age is not None and collection_age > policy.collection_stale_after_minutes:
            warnings.append("collection_heartbeat_stale")
    if research_run is None:
        warnings.append("research_heartbeat_missing")
    else:
        if research_run.status.value == "FAILED":
            failures.append("research_failed")
        if research_age is not None and research_age > policy.research_stale_after_minutes:
            warnings.append("research_heartbeat_stale")

    requests_used = None if usage is None else usage.requests_used
    requests_remaining = None if usage is None else usage.requests_remaining
    local_budget = None if usage is None else usage.local_monthly_budget
    budget_ratio = (
        None
        if requests_used is None or local_budget is None
        else requests_used / local_budget
    )
    if usage is None:
        warnings.append("provider_usage_missing")
    else:
        if requests_remaining == 0:
            failures.append("provider_quota_exhausted")
        if budget_ratio is not None and budget_ratio >= 1.0:
            failures.append("local_credit_budget_exhausted")
        elif budget_ratio is not None and budget_ratio >= policy.budget_warning_fraction:
            warnings.append("local_credit_budget_warning")

    if collection.past_event_without_result_count > 0 and collection.scores_due:
        warnings.append("scores_due_for_missing_results")

    assessment = research.assessment
    if assessment.decisive_event_count > 0:
        if (
            assessment.decision_odds_coverage_rate is not None
            and assessment.decision_odds_coverage_rate < 1.0
        ):
            warnings.append("decision_odds_coverage_gap")
        if (
            assessment.closing_odds_coverage_rate is not None
            and assessment.closing_odds_coverage_rate < 1.0
        ):
            warnings.append("closing_odds_coverage_gap")
    material_blockers = tuple(
        blocker
        for blocker in assessment.blockers
        if blocker != "usable_samples_below_evaluation_minimum"
    )
    if material_blockers:
        warnings.append("research_preflight_blocked")
    odds_delta = None
    result_delta = None
    usable_delta = None
    if previous is not None:
        odds_delta = collection.odds_snapshot_count - previous.odds_snapshot_count
        result_delta = collection.completed_result_count - previous.completed_result_count
        usable_delta = assessment.usable_sample_count - previous.usable_sample_count
        if odds_delta < 0:
            failures.append("odds_snapshot_counter_regressed")
        if result_delta < 0:
            failures.append("completed_result_counter_regressed")
        if usable_delta < 0:
            failures.append("usable_sample_counter_regressed")

    severity = (
        OperationalSeverity.FAIL
        if failures
        else OperationalSeverity.WARN
        if warnings
        else OperationalSeverity.OK
    )
    return OperationalMonitorSnapshotRecord(
        monitor_id=monitor_id or uuid4().hex,
        policy_version=policy.policy_version,
        trigger_kind=trigger_kind,
        checked_at=checked_at,
        severity=severity,
        collection_run_id=None if collection_run is None else collection_run.collection_run_id,
        collection_run_status=None if collection_run is None else collection_run.status,
        collection_age_minutes=collection_age,
        research_run_id=None if research_run is None else research_run.research_run_id,
        research_run_status=None if research_run is None else research_run.status.value,
        research_age_minutes=research_age,
        requests_used=requests_used,
        requests_remaining=requests_remaining,
        local_monthly_budget=local_budget,
        budget_usage_ratio=budget_ratio,
        live_event_count=collection.live_event_count,
        odds_snapshot_count=collection.odds_snapshot_count,
        completed_result_count=collection.completed_result_count,
        past_event_without_result_count=collection.past_event_without_result_count,
        readiness_status=assessment.readiness_status,
        usable_sample_count=assessment.usable_sample_count,
        remaining_to_evaluation=assessment.remaining_to_evaluation,
        remaining_to_validation_samples=assessment.remaining_to_validation_samples,
        decision_odds_coverage_rate=assessment.decision_odds_coverage_rate,
        closing_odds_coverage_rate=assessment.closing_odds_coverage_rate,
        odds_snapshot_delta=odds_delta,
        completed_result_delta=result_delta,
        usable_sample_delta=usable_delta,
        alerts=tuple([*failures, *warnings]),
    )


def _build_operational_snapshot(
    *,
    paths: ProjectPaths,
    checked_at: datetime,
    trigger_kind: str,
    previous: OperationalMonitorSnapshotRecord | None,
) -> OperationalMonitorSnapshotRecord:
    settings = Settings(project_root=paths.root)
    policy = operational_monitoring_policy(settings)
    collection = get_forward_collection_status(
        paths=paths,
        checked_at=checked_at,
        current_min_interval_minutes=settings.forward_current_min_interval_minutes,
        scores_min_interval_minutes=settings.forward_scores_min_interval_minutes,
    )
    research = get_nba_research_readiness_status(
        paths=paths,
        checked_at=checked_at,
        refresh=False,
    )
    usage = get_latest_provider_usage(provider_id=PROVIDER_ID, paths=paths)
    return assess_operational_health(
        collection=collection,
        research=research,
        usage=usage,
        previous=previous,
        policy=policy,
        checked_at=checked_at,
        trigger_kind=trigger_kind,
    )


def get_operational_status(
    *,
    paths: ProjectPaths | None = None,
    checked_at: datetime | None = None,
    refresh: bool = True,
) -> OperationalMonitorSnapshotRecord:
    effective_paths = paths or ProjectPaths.discover()
    latest = get_latest_operational_monitor_snapshot(paths=effective_paths)
    if not refresh and latest is not None:
        return latest
    now = checked_at or datetime.now(UTC)
    return _build_operational_snapshot(
        paths=effective_paths,
        checked_at=now,
        trigger_kind="READ",
        previous=latest,
    )


def run_operational_monitor(
    *,
    paths: ProjectPaths | None = None,
    checked_at: datetime | None = None,
    trigger_kind: str = "MANUAL",
) -> OperationalMonitorSnapshotRecord:
    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    latest = get_latest_operational_monitor_snapshot(paths=effective_paths)
    now = checked_at or datetime.now(UTC)
    record = _build_operational_snapshot(
        paths=effective_paths,
        checked_at=now,
        trigger_kind=trigger_kind,
        previous=latest,
    )
    persist_operational_monitor_snapshot(record, paths=effective_paths)
    return record
