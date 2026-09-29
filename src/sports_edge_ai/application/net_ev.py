from __future__ import annotations

from sports_edge_ai.domain.schemas import PayoutCostRule


def net_ev(
    *,
    model_probability: float,
    decimal_odds: float,
    rule: PayoutCostRule,
) -> float:
    if not 0.0 <= model_probability <= 1.0:
        raise ValueError("model_probability must be between 0 and 1")
    if decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be greater than 1.0")

    expected_payout = model_probability * decimal_odds * rule.payout_factor
    return expected_payout - 1.0 - rule.stake_cost_rate - rule.fixed_cost_per_unit_stake
