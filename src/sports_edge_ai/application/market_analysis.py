from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sports_edge_ai.application.market_baseline import build_market_baseline
from sports_edge_ai.application.net_ev import net_ev
from sports_edge_ai.application.pricing import edge, fair_odds, gross_ev
from sports_edge_ai.application.risk import evaluate_risk
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    MarketAnalysisRecord,
)
from sports_edge_ai.infrastructure.rules_repository import get_payout_cost_rule


def analyze_market(
    *,
    event_id: str,
    decision_as_of: datetime,
    model_probabilities: Mapping[str, float],
    payout_cost_rule_version: str,
    uncertainty: float,
    data_quality: DataQualityStatus,
    model_validated: bool,
    data_conflict: bool = False,
    paths: ProjectPaths | None = None,
) -> tuple[MarketAnalysisRecord, ...]:
    if not 0.0 <= uncertainty <= 1.0:
        raise ValueError("uncertainty must be between 0 and 1")

    effective_paths = paths or ProjectPaths.discover()
    baseline = build_market_baseline(
        event_id=event_id,
        decision_as_of=decision_as_of,
        paths=effective_paths,
        persist=False,
    )
    rule = get_payout_cost_rule(
        rule_version=payout_cost_rule_version,
        decision_as_of=decision_as_of,
        paths=effective_paths,
    )

    baseline_selections = {record.selection for record in baseline.records}
    missing = baseline_selections.difference(model_probabilities)
    extra = set(model_probabilities).difference(baseline_selections)
    if missing or extra:
        raise ValueError(
            "model probabilities must match market selections exactly: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if abs(sum(model_probabilities.values()) - 1.0) > 1e-6:
        raise ValueError("model probabilities must sum to 1.0")

    results: list[MarketAnalysisRecord] = []
    for record in baseline.records:
        model_probability = float(model_probabilities[record.selection])
        if not 0.0 < model_probability < 1.0:
            raise ValueError("model probabilities must be strictly between 0 and 1")

        gross = gross_ev(model_probability, record.decimal_odds)
        net = net_ev(
            model_probability=model_probability,
            decimal_odds=record.decimal_odds,
            rule=rule,
        )
        decision = evaluate_risk(
            net_ev=net,
            uncertainty=uncertainty,
            data_quality=data_quality,
            model_validated=model_validated,
            data_conflict=data_conflict,
        )
        results.append(
            MarketAnalysisRecord(
                event_id=record.event_id,
                market_group_id=record.market_group_id,
                market_id=record.market_id,
                market_type=record.market_type,
                period=record.period,
                selection=record.selection,
                bookmaker=record.bookmaker,
                source=record.source,
                decimal_odds=record.decimal_odds,
                market_probability_fair=record.market_probability_fair,
                model_probability=model_probability,
                model_fair_odds=fair_odds(model_probability),
                edge=edge(model_probability, record.market_probability_fair),
                gross_ev=gross,
                net_ev=net,
                uncertainty=uncertainty,
                data_quality=data_quality,
                recommendation=decision.recommendation,
                risk_blockers=decision.blockers,
                is_model_validated=model_validated,
                payout_cost_rule_version=rule.rule_version,
                decision_as_of=decision_as_of,
                max_input_observed_at=record.max_input_observed_at,
            )
        )

    return tuple(results)
