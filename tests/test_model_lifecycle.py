from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sports_edge_ai.application.calibration import (
    CALIBRATION_VERSION,
    fit_time_separated_platt_calibrator,
)
from sports_edge_ai.application.model_lifecycle import persist_nba_research_lifecycle
from sports_edge_ai.application.nba_baseline import (
    analyze_nba_market,
    fit_nba_logistic_baseline,
)
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.application.validation_gate import evaluate_model_validation
from sports_edge_ai.application.walk_forward_evaluator import evaluate_nba_walk_forward
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    EvidenceTier,
    ModelValidationPolicy,
    NBAMoneylineFeatureRecord,
    NBAMoneylineTrainingSample,
    PayoutCostRule,
)
from sports_edge_ai.infrastructure.db import connect, migrate
from sports_edge_ai.infrastructure.model_store import load_nba_model_artifact

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _samples() -> tuple[NBAMoneylineTrainingSample, ...]:
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rows = (
        (120.0, True),
        (-100.0, False),
        (80.0, True),
        (-60.0, False),
        (150.0, True),
        (-140.0, False),
        (40.0, True),
        (-30.0, False),
        (100.0, True),
        (-90.0, False),
        (20.0, True),
        (-20.0, False),
    )
    result: list[NBAMoneylineTrainingSample] = []
    for index, (rating_diff, home_win) in enumerate(rows):
        decision = start + timedelta(days=index)
        home_favored = rating_diff > 0
        feature = NBAMoneylineFeatureRecord(
            event_id=f"PHASE3B_{index:03d}",
            decision_as_of=decision,
            max_input_observed_at=decision - timedelta(minutes=5),
            home_rating=1500.0 + rating_diff / 2.0,
            away_rating=1500.0 - rating_diff / 2.0,
            home_rest_days=3 if home_favored else 2,
            away_rest_days=2 if home_favored else 3,
        )
        result.append(
            NBAMoneylineTrainingSample(
                features=feature,
                home_win=home_win,
                result_observed_at=decision + timedelta(hours=10),
                home_decimal_odds=1.95 if home_favored else 2.10,
                away_decimal_odds=2.05 if home_favored else 1.95,
                odds_observed_at=decision - timedelta(minutes=1),
                closing_home_decimal_odds=1.82 if home_favored else 2.20,
                closing_away_decimal_odds=2.18 if home_favored else 1.82,
                closing_observed_at=decision + timedelta(hours=8),
                market_home_probability_fair=0.52 if home_favored else 0.48,
            )
        )
    return tuple(result)


def _rule() -> PayoutCostRule:
    return PayoutCostRule(
        rule_version="synthetic-zero-cost-v1",
        jurisdiction="SYNTHETIC",
        market_scope="ALL",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        payout_factor=1.0,
        stake_cost_rate=0.0,
        fixed_cost_per_unit_stake=0.0,
        source_ref="tests",
        verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        production_allowed=False,
    )


def _permissive_policy() -> ModelValidationPolicy:
    return ModelValidationPolicy(
        policy_version="test-permissive-v1",
        min_sample_count=1,
        min_bet_count=1,
        min_brier_improvement=0.0,
        min_log_loss_improvement=0.0,
        max_ece=1.0,
        max_ece_vs_market_delta=1.0,
        min_yield_rate=-1.0,
        min_clv=-1.0,
        max_drawdown=1.0,
        min_bootstrap_ci_low=-1.0,
        max_risk_of_ruin=1.0,
        allowed_evidence_tiers=(EvidenceTier.HISTORICAL_POINT_IN_TIME,),
    )


def _phase3b_objects():
    samples = _samples()
    model = fit_nba_logistic_baseline(samples[:4])
    calibrator = fit_time_separated_platt_calibrator(
        model,
        training_samples=samples[:4],
        calibration_samples=samples[4:6],
    )
    evaluation = evaluate_nba_walk_forward(
        samples,
        payout_cost_rule=_rule(),
        min_train_size=6,
        test_size=2,
        step_size=2,
        calibration_size=2,
        bootstrap_iterations=100,
        bootstrap_seed=11,
    )
    passing_evaluation = evaluation.model_copy(
        update={
            "sample_count": max(1, evaluation.sample_count),
            "bet_count": max(1, evaluation.bet_count),
            "brier": 0.10,
            "market_brier": 0.20,
            "log_loss": 0.30,
            "market_log_loss": 0.60,
            "ece": 0.02,
            "market_ece": 0.03,
            "yield_rate": 0.10,
            "clv": 0.05,
            "max_drawdown": 0.10,
            "bootstrap_ci_low": 0.01,
            "bootstrap_ci_high": 0.20,
            "risk_of_ruin": 0.0,
        }
    )
    return samples, model, calibrator, passing_evaluation


def test_calibration_is_time_separated_and_available_only_after_fit() -> None:
    samples, model, calibrator, _ = _phase3b_objects()

    assert calibrator.record.calibration_version == CALIBRATION_VERSION
    assert calibrator.record.training_window_end <= calibrator.record.calibration_window_start
    with pytest.raises(ValueError, match="not available"):
        calibrator.calibrate(
            model.predict_home_probability(samples[6].features),
            decision_as_of=calibrator.record.fitted_at - timedelta(seconds=1),
        )
    calibrated = calibrator.calibrate(
        model.predict_home_probability(samples[6].features),
        decision_as_of=samples[6].features.decision_as_of,
    )
    assert 0.0 < calibrated < 1.0


def test_calibration_rejects_training_outcome_overlapping_calibration() -> None:
    samples = list(_samples())
    model = fit_nba_logistic_baseline(samples[:4])
    samples[3] = samples[3].model_copy(
        update={"result_observed_at": samples[4].features.decision_as_of + timedelta(minutes=1)}
    )

    with pytest.raises(ValueError, match="known before calibration"):
        fit_time_separated_platt_calibrator(
            model,
            training_samples=samples[:4],
            calibration_samples=samples[4:6],
        )


def test_walk_forward_can_apply_time_separated_calibration() -> None:
    evaluation = evaluate_nba_walk_forward(
        _samples(),
        payout_cost_rule=_rule(),
        min_train_size=6,
        test_size=2,
        step_size=2,
        calibration_size=2,
        bootstrap_iterations=50,
    )

    assert evaluation.calibration_version == CALIBRATION_VERSION
    assert evaluation.fold_count == 3
    assert evaluation.sample_count == 6
    assert evaluation.is_model_validated is False


def test_validation_gate_is_fail_closed_for_synthetic_evidence() -> None:
    _, _, _, evaluation = _phase3b_objects()
    synthetic = evaluate_model_validation(
        evaluation,
        evidence_tier=EvidenceTier.SYNTHETIC,
        policy=_permissive_policy(),
    )
    historical = evaluate_model_validation(
        evaluation,
        evidence_tier=EvidenceTier.HISTORICAL_POINT_IN_TIME,
        policy=_permissive_policy(),
    )

    assert synthetic.is_model_validated is False
    assert "evidence_tier_not_allowed:SYNTHETIC" in synthetic.blockers
    assert historical.is_model_validated is True
    assert historical.blockers == ()


def test_calibrated_probability_flows_through_market_analysis(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(
        PROJECT_ROOT / "fixtures" / "synthetic" / "nba_moneyline_snapshot.json",
        paths=paths,
    )
    _, model, calibrator, _ = _phase3b_objects()
    feature = NBAMoneylineFeatureRecord(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
        max_input_observed_at=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
        home_rating=1560.0,
        away_rating=1440.0,
        home_rest_days=3,
        away_rest_days=2,
    )
    raw_probability = model.predict_home_probability(feature)
    expected_probability = calibrator.calibrate(
        raw_probability,
        decision_as_of=feature.decision_as_of,
    )

    records = analyze_nba_market(
        model=model,
        feature=feature,
        calibrator=calibrator,
        payout_cost_rule_version="synthetic-zero-cost-v1",
        uncertainty=0.10,
        data_quality=DataQualityStatus.GREEN,
        model_validated=False,
        paths=paths,
    )
    by_selection = {record.selection: record for record in records}

    assert by_selection["HOME"].model_probability == pytest.approx(expected_probability)
    assert by_selection["AWAY"].model_probability == pytest.approx(1.0 - expected_probability)


def test_model_artifact_registry_and_backtest_are_portable_and_idempotent(
    tmp_path: Path,
) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    samples, model, calibrator, evaluation = _phase3b_objects()
    gate = evaluate_model_validation(
        evaluation,
        evidence_tier=EvidenceTier.SYNTHETIC,
        policy=_permissive_policy(),
    )
    created_at = datetime(2026, 9, 28, 12, tzinfo=UTC)

    first = persist_nba_research_lifecycle(
        model=model,
        calibrator=calibrator,
        training_samples=samples[:4],
        evaluation=evaluation,
        validation_decision=gate,
        created_at=created_at,
        paths=paths,
    )
    second = persist_nba_research_lifecycle(
        model=model,
        calibrator=calibrator,
        training_samples=samples[:4],
        evaluation=evaluation,
        validation_decision=gate,
        created_at=created_at,
        paths=paths,
    )

    assert first == second
    assert not Path(first.artifact.relative_path).is_absolute()
    assert not Path(first.report_relative_path).is_absolute()
    assert (paths.root / first.artifact.relative_path).is_file()
    assert (paths.root / first.report_relative_path).is_file()
    assert first.registry_record.status == "RESEARCH_NOT_VALIDATED"

    loaded_model, loaded_calibrator = load_nba_model_artifact(
        first.artifact.relative_path,
        paths=paths,
    )
    assert loaded_model == model
    assert loaded_calibrator.record == calibrator.record

    connection = connect(paths)
    try:
        registry_count = connection.execute("SELECT count(*) FROM model_registry").fetchone()[0]
        backtest_count = connection.execute("SELECT count(*) FROM backtest_runs").fetchone()[0]
    finally:
        connection.close()

    assert registry_count == 1
    assert backtest_count == 1
