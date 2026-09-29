from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sports_edge_ai.application.interface_service import get_nba_research_readiness_view
from sports_edge_ai.application.local_nba_modeling import LocalNBAResearchResult
from sports_edge_ai.application.local_nba_research import LocalNBATrainingDataset
from sports_edge_ai.application.research_readiness import (
    assess_nba_training_dataset_readiness,
    nba_research_readiness_policy,
    run_nba_research_cycle,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    EvidenceTier,
    ModelValidationDecision,
    NBAMoneylineFeatureRecord,
    NBAMoneylineTrainingSample,
    Recommendation,
    ResearchCycleStatus,
    ResearchReadinessStatus,
    WalkForwardEvaluationRecord,
)
from sports_edge_ai.infrastructure.db import connect, migrate
from sports_edge_ai.infrastructure.research_readiness_repository import (
    get_latest_research_cycle_run,
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


def _samples(count: int) -> tuple[NBAMoneylineTrainingSample, ...]:
    start = datetime(2025, 1, 1, 12, tzinfo=UTC)
    samples: list[NBAMoneylineTrainingSample] = []
    for index in range(count):
        decision = start + timedelta(days=index)
        home_win = index % 2 == 0
        feature = NBAMoneylineFeatureRecord(
            event_id=f"READY_{index:04d}",
            decision_as_of=decision,
            max_input_observed_at=decision - timedelta(minutes=5),
            home_rating=1510.0 if home_win else 1490.0,
            away_rating=1490.0 if home_win else 1510.0,
            home_rest_days=3,
            away_rest_days=2,
        )
        samples.append(
            NBAMoneylineTrainingSample(
                features=feature,
                home_win=home_win,
                result_observed_at=decision + timedelta(hours=10),
                home_decimal_odds=1.90 if home_win else 2.10,
                away_decimal_odds=2.05 if home_win else 1.90,
                odds_observed_at=decision - timedelta(minutes=1),
                closing_home_decimal_odds=1.85 if home_win else 2.15,
                closing_away_decimal_odds=2.10 if home_win else 1.85,
                closing_observed_at=decision + timedelta(hours=8),
                market_home_probability_fair=0.52 if home_win else 0.48,
            )
        )
    return tuple(samples)


def _dataset(count: int) -> LocalNBATrainingDataset:
    samples = _samples(count)
    return LocalNBATrainingDataset(
        samples=samples,
        candidate_event_count=count,
        skipped_missing_odds=0,
        skipped_non_decisive_result=0,
        decisive_event_count=count,
        decision_odds_covered_count=count,
        closing_odds_covered_count=count,
        skipped_feature_error=0,
    )


def _evaluation(sample_count: int) -> WalkForwardEvaluationRecord:
    start = datetime(2025, 6, 10, 12, tzinfo=UTC)
    return WalkForwardEvaluationRecord(
        model_id="nba-logistic-baseline",
        model_version="nba-logistic-baseline-v1",
        feature_version="nba-moneyline-features-v1",
        calibration_version="platt-v1",
        test_window_start=start,
        test_window_end=start + timedelta(days=max(1, sample_count - 1)),
        fold_count=max(1, sample_count // 20),
        sample_count=sample_count,
        bet_count=max(50, sample_count // 2),
        brier=0.20,
        log_loss=0.60,
        ece=0.03,
        market_brier=0.21,
        market_log_loss=0.61,
        market_ece=0.04,
        roi=0.01,
        yield_rate=0.01,
        clv=0.01,
        max_drawdown=0.10,
        bootstrap_ci_low=0.001,
        bootstrap_ci_high=0.02,
        risk_of_ruin=0.01,
        recommendation=Recommendation.NO_VALIDATED_EDGE,
        is_model_validated=False,
    )


def test_readiness_thresholds_match_walk_forward_and_validation_capacity() -> None:
    checked = datetime(2026, 9, 28, 12, tzinfo=UTC)

    empty = assess_nba_training_dataset_readiness(_dataset(0), checked_at=checked)
    assert empty.readiness_status is ResearchReadinessStatus.NOT_READY
    assert empty.evaluation_min_usable_samples == 180
    assert empty.validation_min_evaluation_samples == 200
    assert empty.validation_min_usable_samples == 360
    assert empty.remaining_to_evaluation == 180
    assert empty.remaining_to_validation_samples == 360

    first_fold = assess_nba_training_dataset_readiness(_dataset(180), checked_at=checked)
    assert first_fold.readiness_status is ResearchReadinessStatus.EVALUATION_READY
    assert first_fold.fold_count_capacity == 1
    assert first_fold.evaluation_sample_capacity == 20
    assert first_fold.ready_for_evaluation is True
    assert first_fold.validation_sample_ready is False
    assert first_fold.evaluation_fingerprint is not None
    assert first_fold.decision_odds_coverage_rate == 1.0
    assert first_fold.closing_odds_coverage_rate == 1.0

    validation_capacity = assess_nba_training_dataset_readiness(
        _dataset(360),
        checked_at=checked,
    )
    assert validation_capacity.readiness_status is ResearchReadinessStatus.VALIDATION_SAMPLE_READY
    assert validation_capacity.fold_count_capacity == 10
    assert validation_capacity.evaluation_sample_capacity == 200
    assert validation_capacity.validation_sample_ready is True
    assert validation_capacity.remaining_to_validation_samples == 0


def test_readiness_blocks_single_class_calibration_window() -> None:
    dataset = _dataset(180)
    mutated = list(dataset.samples)
    for index in range(140, 160):
        mutated[index] = mutated[index].model_copy(update={"home_win": True})
    dataset = LocalNBATrainingDataset(
        samples=tuple(mutated),
        candidate_event_count=180,
        skipped_missing_odds=0,
        skipped_non_decisive_result=0,
        decisive_event_count=180,
        decision_odds_covered_count=180,
        closing_odds_covered_count=180,
        skipped_feature_error=0,
    )

    assessment = assess_nba_training_dataset_readiness(
        dataset,
        checked_at=datetime(2026, 9, 28, 12, tzinfo=UTC),
    )

    assert assessment.readiness_status is ResearchReadinessStatus.NOT_READY
    assert assessment.ready_for_evaluation is False
    assert "fold_0:calibration_single_class" in assessment.blockers


def test_research_cycle_records_not_ready_without_creating_model(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)

    record = run_nba_research_cycle(
        paths=paths,
        checked_at=datetime(2026, 9, 28, 12, tzinfo=UTC),
        trigger_kind="TEST",
    )

    assert record.status is ResearchCycleStatus.NOT_READY
    assert record.usable_sample_count == 0
    assert record.remaining_to_evaluation == 180
    assert record.model_promotion_performed is False
    assert record.report_relative_path is None
    latest = get_latest_research_cycle_run(
        research_key=record.research_key,
        paths=paths,
    )
    assert latest == record
    connection = connect(paths)
    try:
        assert connection.execute("SELECT count(*) FROM model_registry").fetchone()[0] == 0
    finally:
        connection.close()


def test_persisted_readiness_view_does_not_rebuild_dataset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _portable_root(tmp_path)
    checked = datetime(2026, 9, 28, 12, tzinfo=UTC)
    record = run_nba_research_cycle(paths=paths, checked_at=checked, trigger_kind="TEST")

    def fail_rebuild(**kwargs):
        del kwargs
        raise AssertionError("persisted readiness should not rebuild the training dataset")

    monkeypatch.setattr(
        "sports_edge_ai.application.research_readiness.build_local_nba_training_samples",
        fail_rebuild,
    )
    status = get_nba_research_readiness_view(paths=paths)

    assert status.assessment.checked_at == checked
    assert status.assessment.readiness_status is ResearchReadinessStatus.NOT_READY
    assert status.assessment.usable_sample_count == record.usable_sample_count
    assert status.assessment.remaining_to_evaluation == record.remaining_to_evaluation
    assert (
        status.assessment.remaining_to_validation_samples
        == record.remaining_to_validation_samples
    )
    assert status.assessment.blockers == record.blockers
    assert status.latest_run == record


def test_readiness_view_falls_back_to_live_assessment_without_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    calls = {"build": 0}

    def fake_build_local_nba_training_samples(**kwargs):
        del kwargs
        calls["build"] += 1
        return _dataset(0)

    monkeypatch.setattr(
        "sports_edge_ai.application.research_readiness.build_local_nba_training_samples",
        fake_build_local_nba_training_samples,
    )

    status = get_nba_research_readiness_view(paths=paths)

    assert calls["build"] == 1
    assert status.latest_run is None
    assert status.assessment.readiness_status is ResearchReadinessStatus.NOT_READY
    assert status.assessment.usable_sample_count == 0
    assert status.assessment.remaining_to_evaluation == 180
    assert status.assessment.remaining_to_validation_samples == 360
    assert status.assessment.blockers == ("usable_samples_below_evaluation_minimum",)


def test_research_cycle_deduplicates_report_and_never_promotes_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    policy = nba_research_readiness_policy()
    dataset = _dataset(360)
    calls = {"evaluation": 0}

    def fake_assessment_and_dataset(*, paths, policy, checked_at):
        del paths
        return (
            assess_nba_training_dataset_readiness(
                dataset,
                policy=policy,
                checked_at=checked_at,
            ),
            dataset,
        )

    def fake_evaluate(dataset_arg, **kwargs):
        del kwargs
        calls["evaluation"] += 1
        evaluation = _evaluation(200)
        validation = ModelValidationDecision(
            policy_version="nba-research-gate-v1",
            evidence_tier=EvidenceTier.HISTORICAL_POINT_IN_TIME,
            is_model_validated=True,
            blockers=(),
        )
        return LocalNBAResearchResult(
            status="VALIDATED",
            dataset=dataset_arg,
            evaluation=evaluation,
            validation=validation,
        )

    monkeypatch.setattr(
        "sports_edge_ai.application.research_readiness._assessment_and_dataset",
        fake_assessment_and_dataset,
    )
    monkeypatch.setattr(
        "sports_edge_ai.application.research_readiness.evaluate_local_nba_dataset",
        fake_evaluate,
    )

    first = run_nba_research_cycle(
        paths=paths,
        checked_at=datetime(2026, 9, 28, 12, tzinfo=UTC),
        policy=policy,
        trigger_kind="TEST",
    )
    second = run_nba_research_cycle(
        paths=paths,
        checked_at=datetime(2026, 9, 28, 13, tzinfo=UTC),
        policy=policy,
        trigger_kind="TEST",
    )

    assert first.status is ResearchCycleStatus.EVALUATED_GATE_PASSED
    assert first.validation_passed is True
    assert first.model_promotion_performed is False
    assert first.report_relative_path is not None
    report_path = paths.root / first.report_relative_path
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["model_promotion_performed"] is False
    assert report["validation_gate"]["is_model_validated"] is True
    assert second.status is ResearchCycleStatus.SKIPPED_UNCHANGED
    assert second.report_relative_path == first.report_relative_path
    assert calls["evaluation"] == 1

    connection = connect(paths)
    try:
        assert connection.execute("SELECT count(*) FROM model_registry").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM research_readiness_runs").fetchone()[0] == 2
    finally:
        connection.close()
