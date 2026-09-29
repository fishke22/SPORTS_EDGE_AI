from __future__ import annotations

from datetime import datetime

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from sports_edge_ai.application.interface_service import (
    get_backtest_view,
    get_canonical_entities_view,
    get_entity_proposals_view,
    get_event_result_view,
    get_forward_collection_status_view,
    get_mapping_review_summary_view,
    get_market_analysis_view,
    get_market_baseline_view,
    get_model_view,
    get_nba_research_readiness_view,
    get_odds_as_of,
    get_operational_status_view,
    get_paper_portfolio_view,
    get_provider_usage_view,
    get_system_health,
)
from sports_edge_ai.common.logging import configure_logging
from sports_edge_ai.domain.interface_schemas import (
    BacktestLookupResponse,
    CanonicalEntityListResponse,
    EntityProposalListResponse,
    EventResultResponse,
    MarketAnalysisResponse,
    MarketBaselineResponse,
    ModelLookupResponse,
    OddsAsOfResponse,
    PaperPortfolioResponse,
    ProviderUsageResponse,
    SystemHealth,
)
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    ForwardCollectionStatusRecord,
    OperationalMonitorSnapshotRecord,
    ProviderMappingReviewSummary,
    ResearchReadinessStatusRecord,
)

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)

mcp = MCPServer(
    "SPORTS_EDGE_AI",
    version="0.1.0",
    instructions=(
        "Read-only sports-market research tools. Synthetic evidence is not validated betting edge."
    ),
)


@mcp.tool(annotations=READ_ONLY)
def get_system_health_tool() -> SystemHealth:
    """Return portable local database/schema health without mutating state."""
    return get_system_health()


@mcp.tool(annotations=READ_ONLY)
def get_event_odds_tool(event_id: str, as_of: datetime) -> OddsAsOfResponse:
    """Return only odds observable at or before the requested decision time."""
    return get_odds_as_of(event_id=event_id, decision_as_of=as_of)


@mcp.tool(annotations=READ_ONLY)
def get_market_baseline_tool(
    event_id: str,
    as_of: datetime,
) -> MarketBaselineResponse:
    """Return de-vig market baseline records without persisting new data."""
    return get_market_baseline_view(event_id=event_id, decision_as_of=as_of)


@mcp.tool(annotations=READ_ONLY)
def get_market_analysis_tool(
    event_id: str,
    as_of: datetime,
    home_probability: float,
    away_probability: float,
    payout_cost_rule_version: str = "synthetic-zero-cost-v1",
    uncertainty: float = 0.10,
    data_quality: DataQualityStatus = DataQualityStatus.GREEN,
    is_model_validated: bool = False,
    data_conflict: bool = False,
) -> MarketAnalysisResponse:
    """Run shared market analysis using supplied model probabilities."""
    return get_market_analysis_view(
        event_id=event_id,
        decision_as_of=as_of,
        model_probabilities={
            "HOME": home_probability,
            "AWAY": away_probability,
        },
        payout_cost_rule_version=payout_cost_rule_version,
        uncertainty=uncertainty,
        data_quality=data_quality,
        model_validated=is_model_validated,
        data_conflict=data_conflict,
    )


@mcp.tool(annotations=READ_ONLY)
def get_model_tool(model_id: str, model_version: str) -> ModelLookupResponse:
    """Read one model-registry record."""
    return get_model_view(model_id=model_id, model_version=model_version)


@mcp.tool(annotations=READ_ONLY)
def get_backtest_tool(backtest_id: str) -> BacktestLookupResponse:
    """Read one persisted backtest summary."""
    return get_backtest_view(backtest_id=backtest_id)


@mcp.tool(annotations=READ_ONLY)
def get_canonical_entities_tool(
    entity_kind: str,
    sport: str | None = None,
    entity_id_prefix: str | None = None,
) -> CanonicalEntityListResponse:
    """Read canonical entities available for manual provider mapping review."""
    return get_canonical_entities_view(
        entity_kind=entity_kind,
        sport=sport,
        entity_id_prefix=entity_id_prefix,
    )


@mcp.tool(annotations=READ_ONLY)
def get_entity_proposals_tool(
    provider_id: str,
    status: str | None = None,
) -> EntityProposalListResponse:
    """Read provider entity-mapping proposals without approving or rejecting them."""
    return get_entity_proposals_view(provider_id=provider_id, status=status)


@mcp.tool(annotations=READ_ONLY)
def get_mapping_review_summary_tool(
    provider_id: str,
    entity_kind: str,
) -> ProviderMappingReviewSummary:
    """Read mapping-review completion and approved-mapping counts."""
    return get_mapping_review_summary_view(
        provider_id=provider_id,
        entity_kind=entity_kind,
    )


@mcp.tool(annotations=READ_ONLY)
def get_provider_usage_tool(provider_id: str) -> ProviderUsageResponse:
    """Read the latest provider usage/quota snapshot."""
    return get_provider_usage_view(provider_id=provider_id)


@mcp.tool(annotations=READ_ONLY)
def get_forward_collection_status_tool(
    provider_id: str = "provider_the_odds_api",
) -> ForwardCollectionStatusRecord:
    """Read forward-collection freshness, quota, run status, and result coverage."""
    return get_forward_collection_status_view(provider_id=provider_id)


@mcp.tool(annotations=READ_ONLY)
def get_nba_research_readiness_tool() -> ResearchReadinessStatusRecord:
    """Read NBA research sample, odds coverage, temporal, and calibration readiness."""
    return get_nba_research_readiness_view()


@mcp.tool(annotations=READ_ONLY)
def get_operational_status_tool() -> OperationalMonitorSnapshotRecord:
    """Read the latest persisted operational health snapshot."""
    return get_operational_status_view()


@mcp.tool(annotations=READ_ONLY)
def get_event_result_tool(event_id: str) -> EventResultResponse:
    """Read the latest provider-provenanced result for a canonical event."""
    return get_event_result_view(event_id=event_id)


@mcp.tool(annotations=READ_ONLY)
def get_paper_portfolio_tool() -> PaperPortfolioResponse:
    """Read paper-trade positions and realized settlements without mutating state."""
    return get_paper_portfolio_view()


def main() -> None:
    configure_logging()
    mcp.run()


if __name__ == "__main__":
    main()
