from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from sports_edge_ai.application.nba_baseline import (
    NBALogisticBaselineModel,
    analyze_nba_market,
    fit_nba_logistic_baseline,
)
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.application.walk_forward_evaluator import evaluate_nba_walk_forward
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    NBAMoneylineFeatureRecord,
    NBAMoneylineTrainingSample,
    PayoutCostRule,
    Recommendation,
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


def _feature(
    *,
    event_id: str,
    decision_as_of: datetime,
    rating_diff: float,
    rest_diff: int = 0,
) -> NBAMoneylineFeatureRecord:
    home_rest = 2 + max(rest_diff, 0)
    away_rest = 2 + max(-rest_diff, 0)
    return NBAMoneylineFeatureRecord(
        event_id=event_id,
        decision_as_of=decision_as_of,
        max_input_observed_at=decision_as_of - timedelta(minutes=5),
        home_rating=1500.0 + rating_diff / 2.0,
        away_rating=1500.0 - rating_diff / 2.0,
        home_rest_days=home_rest,
        away_rest_days=away_rest,
    )


def _samples() -> tuple[NBAMoneylineTrainingSample, ...]:
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rows = (
        (120.0, 1, True),
        (-100.0, -1, False),
        (80.0, 0, True),
        (-60.0, 0, False),
        (150.0, 1, True),
        (-140.0, -1, False),
        (40.0, 1, True),
        (-30.0, 0, False),
        (100.0, 0, True),
        (-90.0, -1, False),
        (20.0, 1, True),
        (-20.0, 0, False),
    )
    samples: list[NBAMoneylineTrainingSample] = []
    for index, (rating_diff, rest_diff, home_win) in enumerate(rows):
        decision = start + timedelta(days=index)
        home_favored = rating_diff > 0
        samples.append(
            NBAMoneylineTrainingSample(
                features=_feature(
                    event_id=f"SYNTH_NBA_MODEL_{index:03d}",
                    decision_as_of=decision,
                    rating_diff=rating_diff,
                    rest_diff=rest_diff,
                ),
                home_win=home_win,
                closing_observed_at=decision + timedelta(hours=8),
                result_observed_at=decision + timedelta(hours=10),
                home_decimal_odds=1.95 if home_favored else 2.10,
                away_decimal_odds=2.05 if home_favored else 1.95,
                odds_observed_at=decision - timedelta(minutes=1),
                closing_home_decimal_odds=1.82 if home_favored else 2.20,
                closing_away_decimal_odds=2.18 if home_favored else 1.82,
                market_home_probability_fair=0.52 if home_favored else 0.48,
            )
        )
    return tuple(samples)


def _zero_cost_rule() -> PayoutCostRule:
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


def test_feature_contract_rejects_future_input() -> None:
    decision = datetime(2026, 1, 1, 12, tzinfo=UTC)
    with pytest.raises(ValidationError, match="max_input_observed_at"):
        NBAMoneylineFeatureRecord(
            event_id="FUTURE_INPUT",
            decision_as_of=decision,
            max_input_observed_at=decision + timedelta(seconds=1),
            home_rating=1500.0,
            away_rating=1500.0,
            home_rest_days=2,
            away_rest_days=2,
        )


def test_logistic_baseline_is_interpretable_and_directional() -> None:
    samples = _samples()[:8]
    model = fit_nba_logistic_baseline(samples)

    decision = datetime(2026, 2, 1, 12, tzinfo=UTC)
    stronger_home = _feature(
        event_id="STRONG_HOME",
        decision_as_of=decision,
        rating_diff=120.0,
    )
    stronger_away = _feature(
        event_id="STRONG_AWAY",
        decision_as_of=decision,
        rating_diff=-120.0,
    )

    assert model.rating_diff_weight > 0.0
    assert model.predict_home_probability(stronger_home) > 0.5
    assert model.predict_home_probability(stronger_home) > model.predict_home_probability(
        stronger_away
    )


def test_nba_model_probability_flows_through_market_analysis(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(
        PROJECT_ROOT / "fixtures" / "synthetic" / "nba_moneyline_snapshot.json",
        paths=paths,
    )
    model = NBALogisticBaselineModel(
        intercept=0.0,
        rating_diff_weight=0.60,
        rest_diff_weight=0.0,
        home_court_weight=0.0,
    )
    feature = _feature(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
        rating_diff=120.0,
    )

    records = analyze_nba_market(
        model=model,
        feature=feature,
        payout_cost_rule_version="synthetic-zero-cost-v1",
        uncertainty=0.10,
        data_quality=DataQualityStatus.GREEN,
        model_validated=False,
        paths=paths,
    )
    by_selection = {record.selection: record for record in records}

    assert by_selection["HOME"].model_probability > 0.5
    assert by_selection["HOME"].net_ev > 0.0
    assert by_selection["HOME"].recommendation is Recommendation.NO_VALIDATED_EDGE
    assert by_selection["HOME"].is_model_validated is False


def test_walk_forward_outputs_probability_and_betting_metrics() -> None:
    evaluation = evaluate_nba_walk_forward(
        _samples(),
        payout_cost_rule=_zero_cost_rule(),
        min_train_size=4,
        test_size=2,
        step_size=2,
        bootstrap_iterations=200,
        bootstrap_seed=7,
    )

    assert evaluation.fold_count == 4
    assert evaluation.sample_count == 8
    assert evaluation.bet_count > 0
    assert evaluation.brier < evaluation.market_brier
    assert evaluation.log_loss < evaluation.market_log_loss
    assert evaluation.bootstrap_ci_low is not None
    assert evaluation.bootstrap_ci_high is not None
    assert evaluation.bootstrap_ci_low <= evaluation.bootstrap_ci_high
    assert evaluation.clv is not None
    assert evaluation.clv > 0.0
    assert 0.0 <= evaluation.risk_of_ruin <= 1.0
    assert evaluation.recommendation is Recommendation.NO_VALIDATED_EDGE
    assert evaluation.is_model_validated is False
    assert evaluation.test_window_start == _samples()[4].features.decision_as_of
    assert evaluation.test_window_end == _samples()[11].features.decision_as_of


def test_training_sample_rejects_future_decision_odds() -> None:
    sample = _samples()[0]
    with pytest.raises(ValidationError, match="odds_observed_at"):
        NBAMoneylineTrainingSample(
            **sample.model_dump(exclude={"odds_observed_at"}),
            odds_observed_at=sample.features.decision_as_of + timedelta(seconds=1),
        )


def test_walk_forward_rejects_overlapping_test_windows() -> None:
    with pytest.raises(ValueError, match="avoid overlapping tests"):
        evaluate_nba_walk_forward(
            _samples(),
            payout_cost_rule=_zero_cost_rule(),
            min_train_size=4,
            test_size=2,
            step_size=1,
            bootstrap_iterations=10,
        )


def test_walk_forward_rejects_rule_expiring_inside_test_fold() -> None:
    samples = _samples()
    rule = _zero_cost_rule().model_copy(update={"effective_to": samples[5].features.decision_as_of})

    with pytest.raises(ValueError, match="full test fold"):
        evaluate_nba_walk_forward(
            samples,
            payout_cost_rule=rule,
            min_train_size=4,
            test_size=2,
            step_size=2,
            bootstrap_iterations=10,
        )


def test_walk_forward_rejects_label_not_known_at_test_decision() -> None:
    samples = list(_samples()[:6])
    delayed = samples[3].model_copy(
        update={"result_observed_at": samples[4].features.decision_as_of + timedelta(hours=1)}
    )
    samples[3] = delayed

    with pytest.raises(ValueError, match="insufficient settled training"):
        evaluate_nba_walk_forward(
            tuple(samples),
            payout_cost_rule=_zero_cost_rule(),
            min_train_size=4,
            test_size=2,
            bootstrap_iterations=10,
        )
