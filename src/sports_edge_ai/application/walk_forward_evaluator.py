from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

from sports_edge_ai.application.calibration import (
    CALIBRATION_VERSION,
    fit_time_separated_platt_calibrator,
)
from sports_edge_ai.application.nba_baseline import (
    FEATURE_VERSION,
    MODEL_ID,
    MODEL_VERSION,
    fit_nba_logistic_baseline,
)
from sports_edge_ai.domain.schemas import (
    NBAMoneylineTrainingSample,
    PayoutCostRule,
    Recommendation,
    WalkForwardEvaluationRecord,
)


@dataclass(frozen=True, slots=True)
class _Prediction:
    probability: float
    market_probability: float
    outcome: float
    bet_return: float | None
    clv: float | None


def _log_loss(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    epsilon = 1e-12
    losses = []
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        clipped = max(epsilon, min(1.0 - epsilon, probability))
        losses.append(-(outcome * math.log(clipped) + (1.0 - outcome) * math.log(1.0 - clipped)))
    return fmean(losses)


def _brier(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    return fmean(
        (probability - outcome) ** 2
        for probability, outcome in zip(probabilities, outcomes, strict=True)
    )


def _ece(probabilities: Sequence[float], outcomes: Sequence[float], *, bins: int = 10) -> float:
    if bins < 1:
        raise ValueError("bins must be positive")
    bucketed: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        index = min(int(probability * bins), bins - 1)
        bucketed[index].append((probability, outcome))

    total = len(probabilities)
    return sum(
        (len(bucket) / total)
        * abs(
            fmean(probability for probability, _ in bucket)
            - fmean(outcome for _, outcome in bucket)
        )
        for bucket in bucketed
        if bucket
    )


def _realized_return(
    *,
    won: bool,
    decimal_odds: float,
    rule: PayoutCostRule,
) -> float:
    payout = decimal_odds * rule.payout_factor if won else 0.0
    return payout - 1.0 - rule.stake_cost_rate - rule.fixed_cost_per_unit_stake


def _select_bet(
    *,
    probability: float,
    sample: NBAMoneylineTrainingSample,
    rule: PayoutCostRule,
    ev_threshold: float,
) -> tuple[float | None, float | None]:
    home_ev = (
        probability * sample.home_decimal_odds * rule.payout_factor
        - 1.0
        - rule.stake_cost_rate
        - rule.fixed_cost_per_unit_stake
    )
    away_probability = 1.0 - probability
    away_ev = (
        away_probability * sample.away_decimal_odds * rule.payout_factor
        - 1.0
        - rule.stake_cost_rate
        - rule.fixed_cost_per_unit_stake
    )

    if max(home_ev, away_ev) <= ev_threshold:
        return None, None
    if home_ev >= away_ev:
        return (
            _realized_return(
                won=sample.home_win,
                decimal_odds=sample.home_decimal_odds,
                rule=rule,
            ),
            sample.home_decimal_odds / sample.closing_home_decimal_odds - 1.0,
        )
    return (
        _realized_return(
            won=not sample.home_win,
            decimal_odds=sample.away_decimal_odds,
            rule=rule,
        ),
        sample.away_decimal_odds / sample.closing_away_decimal_odds - 1.0,
    )


def _max_drawdown(returns: Sequence[float], *, starting_bankroll: float) -> float:
    bankroll = starting_bankroll
    peak = bankroll
    maximum = 0.0
    for value in returns:
        bankroll += value
        peak = max(peak, bankroll)
        if peak > 0.0:
            maximum = max(maximum, (peak - bankroll) / peak)
    return maximum


def _bootstrap_yield_and_ruin(
    returns: Sequence[float],
    *,
    iterations: int,
    confidence: float,
    starting_bankroll: float,
    seed: int,
) -> tuple[float | None, float | None, float]:
    if not returns:
        return None, None, 0.0
    if iterations < 1:
        raise ValueError("bootstrap iterations must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("bootstrap confidence must be between 0 and 1")

    rng = random.Random(seed)
    simulated_yields: list[float] = []
    ruined = 0
    for _ in range(iterations):
        sampled = [returns[rng.randrange(len(returns))] for _ in returns]
        simulated_yields.append(fmean(sampled))
        bankroll = starting_bankroll
        for value in sampled:
            bankroll += value
            if bankroll <= 0.0:
                ruined += 1
                break

    simulated_yields.sort()
    tail = (1.0 - confidence) / 2.0
    low_index = max(0, min(len(simulated_yields) - 1, int(tail * len(simulated_yields))))
    high_index = max(
        0,
        min(
            len(simulated_yields) - 1,
            int((1.0 - tail) * len(simulated_yields)) - 1,
        ),
    )
    return (
        simulated_yields[low_index],
        simulated_yields[high_index],
        ruined / iterations,
    )


def evaluate_nba_walk_forward(
    samples: Sequence[NBAMoneylineTrainingSample],
    *,
    payout_cost_rule: PayoutCostRule,
    min_train_size: int,
    test_size: int,
    step_size: int | None = None,
    ev_threshold: float = 0.0,
    starting_bankroll: float = 100.0,
    bootstrap_iterations: int = 1000,
    bootstrap_confidence: float = 0.95,
    bootstrap_seed: int = 0,
    calibration_size: int = 0,
) -> WalkForwardEvaluationRecord:
    if min_train_size < 2:
        raise ValueError("min_train_size must be at least two")
    if test_size < 1:
        raise ValueError("test_size must be positive")
    if starting_bankroll <= 0.0:
        raise ValueError("starting_bankroll must be positive")
    if calibration_size < 0:
        raise ValueError("calibration_size must be non-negative")
    if calibration_size and min_train_size < calibration_size + 2:
        raise ValueError(
            "min_train_size must leave at least two base-training samples before calibration"
        )
    effective_step = test_size if step_size is None else step_size
    if effective_step < 1:
        raise ValueError("step_size must be positive")
    if effective_step < test_size:
        raise ValueError("step_size must be at least test_size to avoid overlapping tests")
    if len(samples) < min_train_size + test_size:
        raise ValueError("not enough samples for one walk-forward fold")

    ordered = tuple(samples)
    decision_times = tuple(sample.features.decision_as_of for sample in ordered)
    if any(left > right for left, right in zip(decision_times, decision_times[1:], strict=False)):
        raise ValueError("samples must be nondecreasing by decision_as_of")

    predictions: list[_Prediction] = []
    fold_count = 0
    first_test_time = ordered[min_train_size].features.decision_as_of
    last_test_time = first_test_time
    test_start_index = min_train_size
    while test_start_index + test_size <= len(ordered):
        test = ordered[test_start_index : test_start_index + test_size]
        fold_decision_start = test[0].features.decision_as_of
        fold_decision_end = test[-1].features.decision_as_of
        last_test_time = fold_decision_end
        if not (
            payout_cost_rule.effective_from <= fold_decision_start
            and (
                payout_cost_rule.effective_to is None
                or fold_decision_end < payout_cost_rule.effective_to
            )
        ):
            raise ValueError("payout/cost rule is not effective for the full test fold")
        train = tuple(
            sample
            for sample in ordered[:test_start_index]
            if sample.result_observed_at <= fold_decision_start
        )
        if len(train) < min_train_size:
            raise ValueError("insufficient settled training samples at walk-forward decision time")
        if calibration_size:
            base_train = train[:-calibration_size]
            calibration_samples = train[-calibration_size:]
            model = fit_nba_logistic_baseline(base_train)
            calibrator = fit_time_separated_platt_calibrator(
                model,
                training_samples=base_train,
                calibration_samples=calibration_samples,
            )
            if calibrator.record.fitted_at > fold_decision_start:
                raise RuntimeError("calibrator was fitted after test fold started")
        else:
            model = fit_nba_logistic_baseline(train)
            calibrator = None

        for sample in test:
            raw_probability = model.predict_home_probability(sample.features)
            probability = (
                calibrator.calibrate(
                    raw_probability,
                    decision_as_of=sample.features.decision_as_of,
                )
                if calibrator is not None
                else raw_probability
            )
            bet_return, clv = _select_bet(
                probability=probability,
                sample=sample,
                rule=payout_cost_rule,
                ev_threshold=ev_threshold,
            )
            predictions.append(
                _Prediction(
                    probability=probability,
                    market_probability=sample.market_home_probability_fair,
                    outcome=float(sample.home_win),
                    bet_return=bet_return,
                    clv=clv,
                )
            )
        fold_count += 1
        test_start_index += effective_step

    if not predictions:
        raise ValueError("walk-forward configuration produced no test predictions")

    probabilities = [prediction.probability for prediction in predictions]
    market_probabilities = [prediction.market_probability for prediction in predictions]
    outcomes = [prediction.outcome for prediction in predictions]
    bet_returns = [
        prediction.bet_return for prediction in predictions if prediction.bet_return is not None
    ]
    clv_values = [prediction.clv for prediction in predictions if prediction.clv is not None]
    total_pnl = sum(bet_returns)
    bet_count = len(bet_returns)
    yield_rate = total_pnl / bet_count if bet_count else 0.0
    roi = total_pnl / starting_bankroll
    ci_low, ci_high, risk_of_ruin = _bootstrap_yield_and_ruin(
        bet_returns,
        iterations=bootstrap_iterations,
        confidence=bootstrap_confidence,
        starting_bankroll=starting_bankroll,
        seed=bootstrap_seed,
    )

    return WalkForwardEvaluationRecord(
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        calibration_version=(CALIBRATION_VERSION if calibration_size else "uncalibrated-v1"),
        test_window_start=first_test_time,
        test_window_end=last_test_time,
        fold_count=fold_count,
        sample_count=len(predictions),
        bet_count=bet_count,
        brier=_brier(probabilities, outcomes),
        log_loss=_log_loss(probabilities, outcomes),
        ece=_ece(probabilities, outcomes),
        market_brier=_brier(market_probabilities, outcomes),
        market_log_loss=_log_loss(market_probabilities, outcomes),
        market_ece=_ece(market_probabilities, outcomes),
        roi=roi,
        yield_rate=yield_rate,
        clv=fmean(clv_values) if clv_values else None,
        max_drawdown=_max_drawdown(bet_returns, starting_bankroll=starting_bankroll),
        bootstrap_ci_low=ci_low,
        bootstrap_ci_high=ci_high,
        risk_of_ruin=risk_of_ruin,
        recommendation=Recommendation.NO_VALIDATED_EDGE,
        is_model_validated=False,
    )
