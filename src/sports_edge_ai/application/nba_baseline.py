from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sports_edge_ai.application.market_analysis import analyze_market
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    MarketAnalysisRecord,
    NBAMoneylineFeatureRecord,
    NBAMoneylineTrainingSample,
)

if TYPE_CHECKING:
    from sports_edge_ai.application.calibration import PlattCalibrator

MODEL_ID = "nba-logistic-baseline"
MODEL_VERSION = "nba-logistic-baseline-v1"
FEATURE_VERSION = "nba-moneyline-features-v1"


@dataclass(frozen=True, slots=True)
class NBALogisticBaselineModel:
    intercept: float
    rating_diff_weight: float
    rest_diff_weight: float
    home_court_weight: float
    model_id: str = MODEL_ID
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION

    def predict_home_probability(self, feature: NBAMoneylineFeatureRecord) -> float:
        if feature.feature_version != self.feature_version:
            raise ValueError(
                f"feature version mismatch: {feature.feature_version!r} != {self.feature_version!r}"
            )
        rating_diff = (feature.home_rating - feature.away_rating) / 100.0
        rest_diff = float(feature.home_rest_days - feature.away_rest_days)
        home_court = 0.0 if feature.neutral_site else 1.0
        score = (
            self.intercept
            + self.rating_diff_weight * rating_diff
            + self.rest_diff_weight * rest_diff
            + self.home_court_weight * home_court
        )
        return _sigmoid(score)

    def predict_market_probabilities(self, feature: NBAMoneylineFeatureRecord) -> dict[str, float]:
        home_probability = self.predict_home_probability(feature)
        return {"HOME": home_probability, "AWAY": 1.0 - home_probability}


def _sigmoid(value: float) -> float:
    clipped = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-clipped))


def _feature_vector(feature: NBAMoneylineFeatureRecord) -> tuple[float, float, float]:
    return (
        (feature.home_rating - feature.away_rating) / 100.0,
        float(feature.home_rest_days - feature.away_rest_days),
        0.0 if feature.neutral_site else 1.0,
    )


def fit_nba_logistic_baseline(
    samples: Sequence[NBAMoneylineTrainingSample],
    *,
    learning_rate: float = 0.08,
    epochs: int = 800,
    l2_penalty: float = 0.01,
) -> NBALogisticBaselineModel:
    if len(samples) < 2:
        raise ValueError("at least two training samples are required")
    if learning_rate <= 0.0:
        raise ValueError("learning_rate must be positive")
    if epochs < 1:
        raise ValueError("epochs must be positive")
    if l2_penalty < 0.0:
        raise ValueError("l2_penalty must be non-negative")
    labels = {sample.home_win for sample in samples}
    if len(labels) < 2:
        raise ValueError("training samples must contain both outcome classes")
    if any(sample.features.feature_version != FEATURE_VERSION for sample in samples):
        raise ValueError("training samples contain unsupported feature versions")

    weights = [0.0, 0.0, 0.0, 0.0]
    sample_count = float(len(samples))

    for _ in range(epochs):
        gradients = [0.0, 0.0, 0.0, 0.0]
        for sample in samples:
            rating_diff, rest_diff, home_court = _feature_vector(sample.features)
            vector = (1.0, rating_diff, rest_diff, home_court)
            score = sum(weight * value for weight, value in zip(weights, vector, strict=True))
            error = _sigmoid(score) - float(sample.home_win)
            for index, value in enumerate(vector):
                gradients[index] += error * value

        for index in range(4):
            gradient = gradients[index] / sample_count
            if index > 0:
                gradient += l2_penalty * weights[index]
            weights[index] -= learning_rate * gradient

    return NBALogisticBaselineModel(
        intercept=weights[0],
        rating_diff_weight=weights[1],
        rest_diff_weight=weights[2],
        home_court_weight=weights[3],
    )


def analyze_nba_market(
    *,
    model: NBALogisticBaselineModel,
    feature: NBAMoneylineFeatureRecord,
    payout_cost_rule_version: str,
    uncertainty: float,
    data_quality: DataQualityStatus,
    model_validated: bool = False,
    data_conflict: bool = False,
    calibrator: PlattCalibrator | None = None,
    paths: ProjectPaths | None = None,
) -> tuple[MarketAnalysisRecord, ...]:
    raw_home_probability = model.predict_home_probability(feature)
    home_probability = (
        calibrator.calibrate(
            raw_home_probability,
            decision_as_of=feature.decision_as_of,
        )
        if calibrator is not None
        else raw_home_probability
    )
    return analyze_market(
        event_id=feature.event_id,
        decision_as_of=feature.decision_as_of,
        model_probabilities={"HOME": home_probability, "AWAY": 1.0 - home_probability},
        payout_cost_rule_version=payout_cost_rule_version,
        uncertainty=uncertainty,
        data_quality=data_quality,
        model_validated=model_validated,
        data_conflict=data_conflict,
        paths=paths,
    )
