from __future__ import annotations

from sports_edge_ai.domain.schemas import (
    EvidenceTier,
    ModelValidationDecision,
    ModelValidationPolicy,
    WalkForwardEvaluationRecord,
)


def research_validation_policy() -> ModelValidationPolicy:
    return ModelValidationPolicy(
        policy_version="nba-research-gate-v1",
        min_sample_count=200,
        min_bet_count=50,
        min_brier_improvement=0.0,
        min_log_loss_improvement=0.0,
        max_ece=0.05,
        max_ece_vs_market_delta=0.0,
        min_yield_rate=0.0,
        min_clv=0.0,
        max_drawdown=0.25,
        min_bootstrap_ci_low=0.0,
        max_risk_of_ruin=0.05,
        allowed_evidence_tiers=(EvidenceTier.HISTORICAL_POINT_IN_TIME,),
    )


def evaluate_model_validation(
    evaluation: WalkForwardEvaluationRecord,
    *,
    evidence_tier: EvidenceTier,
    policy: ModelValidationPolicy,
) -> ModelValidationDecision:
    blockers: list[str] = []

    if evidence_tier not in policy.allowed_evidence_tiers:
        blockers.append(f"evidence_tier_not_allowed:{evidence_tier.value}")
    if evaluation.sample_count < policy.min_sample_count:
        blockers.append("sample_count_below_minimum")
    if evaluation.bet_count < policy.min_bet_count:
        blockers.append("bet_count_below_minimum")
    if evaluation.market_brier - evaluation.brier <= policy.min_brier_improvement:
        blockers.append("brier_not_better_than_market")
    if evaluation.market_log_loss - evaluation.log_loss <= policy.min_log_loss_improvement:
        blockers.append("log_loss_not_better_than_market")
    if evaluation.ece > policy.max_ece:
        blockers.append("ece_above_maximum")
    if evaluation.ece - evaluation.market_ece > policy.max_ece_vs_market_delta:
        blockers.append("ece_worse_than_market")
    if evaluation.yield_rate < policy.min_yield_rate:
        blockers.append("yield_below_minimum")
    if evaluation.clv is None or evaluation.clv < policy.min_clv:
        blockers.append("clv_below_minimum")
    if evaluation.max_drawdown > policy.max_drawdown:
        blockers.append("max_drawdown_above_maximum")
    if (
        evaluation.bootstrap_ci_low is None
        or evaluation.bootstrap_ci_low < policy.min_bootstrap_ci_low
    ):
        blockers.append("bootstrap_ci_low_below_minimum")
    if evaluation.risk_of_ruin > policy.max_risk_of_ruin:
        blockers.append("risk_of_ruin_above_maximum")

    validated = not blockers
    return ModelValidationDecision(
        policy_version=policy.policy_version,
        evidence_tier=evidence_tier,
        is_model_validated=validated,
        blockers=tuple(blockers),
    )
