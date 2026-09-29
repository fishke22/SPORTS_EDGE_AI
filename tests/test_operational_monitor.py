from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sports_edge_ai.application.operational_monitor import (
    assess_operational_health,
    operational_monitoring_policy,
    run_operational_monitor,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.domain.schemas import (
    ForwardCollectionRunRecord,
    ForwardCollectionStatusRecord,
    OperationalMonitorSnapshotRecord,
    OperationalSeverity,
    ProviderUsageSnapshot,
    ResearchCycleRunRecord,
    ResearchCycleStatus,
    ResearchReadinessAssessment,
    ResearchReadinessStatus,
    ResearchReadinessStatusRecord,
)
from sports_edge_ai.infrastructure.operational_monitor_repository import (
    get_latest_operational_monitor_snapshot,
)

PROJECT_ROOT = Path(__file__).parents[1]
def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _collection(now: datetime, *, status: str = "SUCCESS", age_minutes: int = 30,
                odds_count: int = 120, result_count: int = 0,
                result_gap: int = 0, scores_due: bool = False) -> ForwardCollectionStatusRecord:
    run = ForwardCollectionRunRecord(
        collection_run_id="collection-run",
        provider_id="provider_the_odds_api",
        trigger_kind="TEST",
        started_at=now - timedelta(minutes=age_minutes + 1),
        finished_at=now - timedelta(minutes=age_minutes),
        status=status,
        current_due=False,
        scores_due=scores_due,
        current_attempted=False,
        scores_attempted=False,
        events_count=0,
        odds_count=0,
        results_count=0,
        unresolved_count=0,
        credits_spent=0,
    )
    return ForwardCollectionStatusRecord(
        provider_id="provider_the_odds_api",
        checked_at=now,
        current_min_interval_minutes=180,
        scores_min_interval_minutes=720,
        current_due=False,
        scores_due=scores_due,
        latest_run=run,
        requests_used=10,
        requests_remaining=490,
        live_event_count=41,
        odds_snapshot_count=odds_count,
        completed_result_count=result_count,
        past_event_without_result_count=result_gap,
    )


def _research(now: datetime, *, age_minutes: int = 20, usable: int = 0,
              decisive: int = 0, decision_coverage: float | None = None,
              closing_coverage: float | None = None,
              blockers: tuple[str, ...] = ("usable_samples_below_evaluation_minimum",)
              ) -> ResearchReadinessStatusRecord:
    assessment = ResearchReadinessAssessment(
        research_key="nba-pregame-moneyline-v1",
        checked_at=now - timedelta(minutes=age_minutes),
        readiness_policy_version="nba-readiness-v1",
        validation_policy_version="nba-research-gate-v1",
        readiness_status=ResearchReadinessStatus.NOT_READY,
        dataset_fingerprint="a" * 64,
        candidate_event_count=decisive,
        decisive_event_count=decisive,
        usable_sample_count=usable,
        decision_odds_covered_count=(
            0 if decision_coverage is None else round(decisive * decision_coverage)
        ),
        closing_odds_covered_count=(
            0 if closing_coverage is None else round(decisive * closing_coverage)
        ),
        decision_odds_coverage_rate=decision_coverage,
        closing_odds_coverage_rate=closing_coverage,
        skipped_missing_odds=0,
        skipped_non_decisive_result=0,
        skipped_feature_error=0,
        decision_horizon_hours=6,
        min_train_size=160,
        test_size=20,
        calibration_size=20,
        bootstrap_iterations=1000,
        evaluation_min_usable_samples=180,
        evaluation_sample_capacity=0,
        validation_min_evaluation_samples=200,
        validation_min_usable_samples=360,
        remaining_to_evaluation=max(0, 180 - usable),
        remaining_to_validation_samples=max(0, 360 - usable),
        fold_count_capacity=0,
        ready_for_evaluation=False,
        validation_sample_ready=False,
        blockers=blockers,
    )
    run = ResearchCycleRunRecord(
        research_run_id="research-run",
        research_key=assessment.research_key,
        readiness_policy_version=assessment.readiness_policy_version,
        validation_policy_version=assessment.validation_policy_version,
        trigger_kind="TEST",
        checked_at=assessment.checked_at,
        status=ResearchCycleStatus.NOT_READY,
        dataset_fingerprint=assessment.dataset_fingerprint,
        decision_horizon_hours=6,
        min_train_size=160,
        test_size=20,
        calibration_size=20,
        bootstrap_iterations=1000,
        candidate_event_count=decisive,
        decisive_event_count=decisive,
        usable_sample_count=usable,
        decision_odds_covered_count=assessment.decision_odds_covered_count,
        closing_odds_covered_count=assessment.closing_odds_covered_count,
        skipped_missing_odds=0,
        skipped_non_decisive_result=0,
        skipped_feature_error=0,
        evaluation_min_usable_samples=180,
        evaluation_sample_capacity=0,
        validation_min_evaluation_samples=200,
        validation_min_usable_samples=360,
        remaining_to_evaluation=max(0, 180 - usable),
        remaining_to_validation_samples=max(0, 360 - usable),
        fold_count_capacity=0,
        ready_for_evaluation=False,
        validation_sample_ready=False,
        blockers=blockers,
    )
    return ResearchReadinessStatusRecord(assessment=assessment, latest_run=run)


def _usage(now: datetime, *, used: int = 10, remaining: int = 490) -> ProviderUsageSnapshot:
    return ProviderUsageSnapshot(
        provider_id="provider_the_odds_api",
        observed_at=now,
        requests_remaining=remaining,
        requests_used=used,
        requests_last=1,
        local_monthly_budget=450,
        endpoint_kind="current_nba_h2h",
    )


def _previous(now: datetime, *, odds: int = 100, results: int = 0,
              usable: int = 0) -> OperationalMonitorSnapshotRecord:
    return OperationalMonitorSnapshotRecord(
        monitor_id="previous",
        policy_version="operational-monitor-v1",
        trigger_kind="TEST",
        checked_at=now - timedelta(hours=1),
        severity=OperationalSeverity.OK,
        live_event_count=40,
        odds_snapshot_count=odds,
        completed_result_count=results,
        past_event_without_result_count=0,
        readiness_status=ResearchReadinessStatus.NOT_READY,
        usable_sample_count=usable,
        remaining_to_evaluation=max(0, 180 - usable),
        remaining_to_validation_samples=max(0, 360 - usable),
    )


def test_operational_health_is_ok_when_heartbeats_and_budget_are_safe() -> None:
    now = datetime(2026, 9, 29, 11, tzinfo=UTC)
    policy = operational_monitoring_policy(Settings())

    record = assess_operational_health(
        collection=_collection(now),
        research=_research(now),
        usage=_usage(now),
        previous=_previous(now),
        policy=policy,
        checked_at=now,
        trigger_kind="TEST",
        monitor_id="healthy",
    )

    assert record.severity is OperationalSeverity.OK
    assert record.alerts == ()
    assert record.odds_snapshot_delta == 20
    assert record.completed_result_delta == 0
    assert record.usable_sample_delta == 0
def test_operational_health_warns_on_stale_budget_and_coverage_gaps() -> None:
    now = datetime(2026, 9, 29, 11, tzinfo=UTC)
    policy = operational_monitoring_policy(Settings())
    research = _research(
        now,
        age_minutes=200,
        decisive=10,
        decision_coverage=0.8,
        closing_coverage=0.6,
        blockers=("fold_0:calibration_single_class",),
    )

    record = assess_operational_health(
        collection=_collection(now, age_minutes=200, result_gap=2, scores_due=True),
        research=research,
        usage=_usage(now, used=400, remaining=100),
        previous=None,
        policy=policy,
        checked_at=now,
        trigger_kind="TEST",
    )

    assert record.severity is OperationalSeverity.WARN
    assert "collection_heartbeat_stale" in record.alerts
    assert "research_heartbeat_stale" in record.alerts
    assert "local_credit_budget_warning" in record.alerts
    assert "scores_due_for_missing_results" in record.alerts
    assert "decision_odds_coverage_gap" in record.alerts
    assert "closing_odds_coverage_gap" in record.alerts
    assert "research_preflight_blocked" in record.alerts
def test_operational_health_fails_on_run_failure_quota_and_counter_regression() -> None:
    now = datetime(2026, 9, 29, 11, tzinfo=UTC)
    policy = operational_monitoring_policy(Settings())

    record = assess_operational_health(
        collection=_collection(now, status="FAILED", odds_count=90, result_count=1),
        research=_research(now, usable=1),
        usage=_usage(now, used=450, remaining=0),
        previous=_previous(now, odds=100, results=2, usable=2),
        policy=policy,
        checked_at=now,
        trigger_kind="TEST",
    )

    assert record.severity is OperationalSeverity.FAIL
    assert "collection_failed" in record.alerts
    assert "provider_quota_exhausted" in record.alerts
    assert "local_credit_budget_exhausted" in record.alerts
    assert "odds_snapshot_counter_regressed" in record.alerts
    assert "completed_result_counter_regressed" in record.alerts
    assert "usable_sample_counter_regressed" in record.alerts
def test_operational_monitor_persists_snapshot_on_empty_portable_root(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    now = datetime(2026, 9, 29, 11, tzinfo=UTC)

    record = run_operational_monitor(
        paths=paths,
        checked_at=now,
        trigger_kind="TEST",
    )
    latest = get_latest_operational_monitor_snapshot(paths=paths)

    assert record.severity is OperationalSeverity.WARN
    assert "collection_heartbeat_missing" in record.alerts
    assert "research_heartbeat_missing" in record.alerts
    assert "provider_usage_missing" in record.alerts
    assert latest == record
