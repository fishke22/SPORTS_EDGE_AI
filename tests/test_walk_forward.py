from datetime import UTC, datetime, timedelta

import pytest

from sports_edge_ai.application.walk_forward import build_expanding_walk_forward_plan
from sports_edge_ai.domain.schemas import Recommendation


def test_walk_forward_plan_preserves_temporal_order() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = tuple(start + timedelta(days=index) for index in range(8))

    plan = build_expanding_walk_forward_plan(
        timestamps,
        min_train_size=4,
        test_size=2,
        step_size=2,
    )

    assert len(plan.folds) == 2
    assert plan.recommendation is Recommendation.NO_VALIDATED_EDGE
    assert plan.validated_edge is False
    assert all(fold.train_end < fold.test_start for fold in plan.folds)
    assert [fold.train_count for fold in plan.folds] == [4, 6]
    assert [fold.test_count for fold in plan.folds] == [2, 2]


def test_walk_forward_rejects_unsorted_or_duplicate_timestamps() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="strictly increasing"):
        build_expanding_walk_forward_plan(
            (timestamp, timestamp),
            min_train_size=1,
            test_size=1,
        )
