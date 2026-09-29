from __future__ import annotations

from collections.abc import Mapping


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be greater than 1.0")
    return 1.0 / decimal_odds


def devig_multiplicative(odds_by_selection: Mapping[str, float]) -> dict[str, float]:
    if len(odds_by_selection) < 2:
        raise ValueError("at least two selections are required to de-vig a market")
    raw = {selection: implied_probability(odds) for selection, odds in odds_by_selection.items()}
    overround = sum(raw.values())
    if overround <= 0.0:
        raise ValueError("market implied probability total must be positive")
    return {selection: probability / overround for selection, probability in raw.items()}


def fair_odds(probability: float) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must be strictly between 0 and 1")
    return 1.0 / probability


def edge(model_probability: float, market_probability: float) -> float:
    for value in (model_probability, market_probability):
        if not 0.0 <= value <= 1.0:
            raise ValueError("probabilities must be between 0 and 1")
    return model_probability - market_probability


def gross_ev(model_probability: float, decimal_odds: float) -> float:
    if not 0.0 <= model_probability <= 1.0:
        raise ValueError("model_probability must be between 0 and 1")
    if decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be greater than 1.0")
    return model_probability * decimal_odds - 1.0
