from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sports_edge_ai.domain.schemas import Recommendation, WalkForwardFold


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    folds: tuple[WalkForwardFold, ...]
    recommendation: Recommendation
    validated_edge: bool


def build_expanding_walk_forward_plan(
    timestamps: tuple[datetime, ...],
    *,
    min_train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> WalkForwardPlan:
    if min_train_size < 1:
        raise ValueError("min_train_size must be positive")
    if test_size < 1:
        raise ValueError("test_size must be positive")
    effective_step = test_size if step_size is None else step_size
    if effective_step < 1:
        raise ValueError("step_size must be positive")
    if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
        raise ValueError("walk-forward timestamps must be timezone-aware")
    if any(left >= right for left, right in zip(timestamps, timestamps[1:], strict=False)):
        raise ValueError("walk-forward timestamps must be strictly increasing")

    folds: list[WalkForwardFold] = []
    test_start_index = min_train_size
    fold_index = 0
    while test_start_index + test_size <= len(timestamps):
        train = timestamps[:test_start_index]
        test = timestamps[test_start_index : test_start_index + test_size]
        if train[-1] >= test[0]:
            raise RuntimeError("walk-forward leakage: train_end must precede test_start")
        folds.append(
            WalkForwardFold(
                fold_index=fold_index,
                train_start=train[0],
                train_end=train[-1],
                test_start=test[0],
                test_end=test[-1],
                train_count=len(train),
                test_count=len(test),
            )
        )
        fold_index += 1
        test_start_index += effective_step

    return WalkForwardPlan(
        folds=tuple(folds),
        recommendation=Recommendation.NO_VALIDATED_EDGE,
        validated_edge=False,
    )
