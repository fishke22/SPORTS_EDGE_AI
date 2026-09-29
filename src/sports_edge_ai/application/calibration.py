from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sports_edge_ai.application.nba_baseline import NBALogisticBaselineModel
from sports_edge_ai.domain.schemas import CalibrationRecord, NBAMoneylineTrainingSample

CALIBRATION_VERSION = "platt-v1"


@dataclass(frozen=True, slots=True)
class PlattCalibrator:
    record: CalibrationRecord

    def calibrate(self, probability: float, *, decision_as_of: datetime) -> float:
        if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
            raise ValueError("decision_as_of must be timezone-aware")
        if not 0.0 < probability < 1.0:
            raise ValueError("probability must be strictly between 0 and 1")
        if decision_as_of < self.record.fitted_at:
            raise ValueError("calibrator was not available at decision_as_of")
        logit = math.log(probability / (1.0 - probability))
        score = self.record.intercept + self.record.slope * logit
        clipped = max(-35.0, min(35.0, score))
        return 1.0 / (1.0 + math.exp(-clipped))


def fit_time_separated_platt_calibrator(
    model: NBALogisticBaselineModel,
    *,
    training_samples: Sequence[NBAMoneylineTrainingSample],
    calibration_samples: Sequence[NBAMoneylineTrainingSample],
    learning_rate: float = 0.05,
    epochs: int = 1000,
    l2_penalty: float = 0.01,
) -> PlattCalibrator:
    if not training_samples:
        raise ValueError("training_samples must not be empty")
    if len(calibration_samples) < 2:
        raise ValueError("at least two calibration samples are required")
    if learning_rate <= 0.0:
        raise ValueError("learning_rate must be positive")
    if epochs < 1:
        raise ValueError("epochs must be positive")
    if l2_penalty < 0.0:
        raise ValueError("l2_penalty must be non-negative")

    calibration_times = tuple(sample.features.decision_as_of for sample in calibration_samples)
    if any(
        left > right for left, right in zip(calibration_times, calibration_times[1:], strict=False)
    ):
        raise ValueError("calibration samples must be nondecreasing by decision time")

    training_window_end = max(sample.result_observed_at for sample in training_samples)
    calibration_window_start = calibration_samples[0].features.decision_as_of
    if training_window_end > calibration_window_start:
        raise ValueError("training outcomes must be known before calibration window starts")
    if len({sample.home_win for sample in calibration_samples}) < 2:
        raise ValueError("calibration samples must contain both outcome classes")

    intercept = 0.0
    slope = 1.0
    count = float(len(calibration_samples))
    for _ in range(epochs):
        intercept_gradient = 0.0
        slope_gradient = 0.0
        for sample in calibration_samples:
            raw_probability = model.predict_home_probability(sample.features)
            raw_logit = math.log(raw_probability / (1.0 - raw_probability))
            score = intercept + slope * raw_logit
            clipped = max(-35.0, min(35.0, score))
            predicted = 1.0 / (1.0 + math.exp(-clipped))
            error = predicted - float(sample.home_win)
            intercept_gradient += error
            slope_gradient += error * raw_logit

        intercept -= learning_rate * (intercept_gradient / count)
        slope_gradient = slope_gradient / count + l2_penalty * (slope - 1.0)
        slope -= learning_rate * slope_gradient

    fitted_at = max(sample.result_observed_at for sample in calibration_samples)
    return PlattCalibrator(
        record=CalibrationRecord(
            calibration_version=CALIBRATION_VERSION,
            model_id=model.model_id,
            model_version=model.model_version,
            feature_version=model.feature_version,
            training_window_end=training_window_end,
            calibration_window_start=calibration_window_start,
            calibration_window_end=calibration_samples[-1].features.decision_as_of,
            fitted_at=fitted_at,
            sample_count=len(calibration_samples),
            intercept=intercept,
            slope=slope,
        )
    )
