import pytest

from sports_edge_ai.application.pricing import devig_multiplicative, gross_ev
from sports_edge_ai.application.risk import evaluate_risk
from sports_edge_ai.domain.schemas import DataQualityStatus, Recommendation


def test_devig_probabilities_sum_to_one() -> None:
    fair = devig_multiplicative({"home": 1.80, "away": 2.10})

    assert sum(fair.values()) == pytest.approx(1.0)
    assert fair["home"] > fair["away"]


def test_gross_ev_uses_probability_and_price() -> None:
    assert gross_ev(0.55, 2.0) == pytest.approx(0.10)


def test_positive_ev_is_not_edge_until_model_is_validated() -> None:
    decision = evaluate_risk(
        net_ev=0.05,
        uncertainty=0.10,
        data_quality=DataQualityStatus.GREEN,
        model_validated=False,
    )

    assert decision.recommendation is Recommendation.NO_VALIDATED_EDGE
    assert decision.blockers == ("MODEL_NOT_VALIDATED",)


def test_red_data_quality_vetoes_signal() -> None:
    decision = evaluate_risk(
        net_ev=0.10,
        uncertainty=0.05,
        data_quality=DataQualityStatus.RED,
        model_validated=True,
    )

    assert decision.recommendation is Recommendation.NO_BET
