from __future__ import annotations

from dataclasses import dataclass

from sports_edge_ai.domain.schemas import DataQualityStatus, Recommendation


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    edge_net_ev: float = 0.02
    max_uncertainty: float = 0.25


@dataclass(frozen=True, slots=True)
class RiskDecision:
    recommendation: Recommendation
    blockers: tuple[str, ...]


def evaluate_risk(
    *,
    net_ev: float,
    uncertainty: float,
    data_quality: DataQualityStatus,
    model_validated: bool,
    data_conflict: bool = False,
    policy: RiskPolicy | None = None,
) -> RiskDecision:
    effective_policy = policy or RiskPolicy()

    if data_conflict:
        return RiskDecision(Recommendation.DATA_CONFLICT, ("DATA_CONFLICT",))
    if data_quality is DataQualityStatus.RED:
        return RiskDecision(Recommendation.NO_BET, ("DATA_QUALITY_RED",))
    if net_ev <= 0.0:
        return RiskDecision(Recommendation.NO_BET, ("NON_POSITIVE_NET_EV",))
    if not model_validated:
        return RiskDecision(Recommendation.NO_VALIDATED_EDGE, ("MODEL_NOT_VALIDATED",))

    blockers: list[str] = []
    if data_quality is DataQualityStatus.YELLOW:
        blockers.append("DATA_QUALITY_YELLOW")
    if uncertainty > effective_policy.max_uncertainty:
        blockers.append("UNCERTAINTY_TOO_HIGH")
    if net_ev < effective_policy.edge_net_ev:
        blockers.append("NET_EV_BELOW_EDGE_GATE")
    if blockers:
        return RiskDecision(Recommendation.WATCH, tuple(blockers))

    return RiskDecision(Recommendation.EDGE, ())
