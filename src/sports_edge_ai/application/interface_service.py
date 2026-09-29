from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sports_edge_ai.application.entity_mapping import (
    get_mapping_review_summary,
    list_canonical_entities,
    list_entity_proposals,
)
from sports_edge_ai.application.forward_collection import get_forward_collection_status
from sports_edge_ai.application.market_analysis import analyze_market
from sports_edge_ai.application.market_baseline import build_market_baseline
from sports_edge_ai.application.operational_monitor import get_operational_status
from sports_edge_ai.application.research_readiness import get_nba_research_readiness_status
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.domain.interface_schemas import (
    BacktestLookupResponse,
    CanonicalEntityListResponse,
    EntityProposalListResponse,
    EventResultResponse,
    MarketAnalysisResponse,
    MarketBaselineResponse,
    ModelLookupResponse,
    OddsAsOfItem,
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
from sports_edge_ai.infrastructure.db import current_schema_version
from sports_edge_ai.infrastructure.model_repository import (
    get_backtest_record,
    get_model_registry_record,
)
from sports_edge_ai.infrastructure.odds_repository import get_event_odds_as_of
from sports_edge_ai.infrastructure.paper_trade_repository import (
    list_paper_trades,
    list_settlements,
)
from sports_edge_ai.infrastructure.provider_usage_repository import get_latest_provider_usage
from sports_edge_ai.infrastructure.providers.the_odds_api import PROVIDER_ID
from sports_edge_ai.infrastructure.result_repository import get_latest_event_result


def get_system_health(*, paths: ProjectPaths | None = None) -> SystemHealth:
    effective_paths = paths or ProjectPaths.discover()
    schema_version = current_schema_version(effective_paths)
    return SystemHealth(
        status="ok" if schema_version is not None else "uninitialized",
        database_ready=schema_version is not None,
        schema_version=schema_version,
    )


def get_odds_as_of(
    *,
    event_id: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
) -> OddsAsOfResponse:
    rows = get_event_odds_as_of(
        event_id=event_id,
        decision_as_of=decision_as_of,
        paths=paths,
    )
    return OddsAsOfResponse(
        event_id=event_id,
        as_of=decision_as_of,
        odds=tuple(
            OddsAsOfItem(
                market_id=row.market_id,
                bookmaker=row.bookmaker,
                source=row.source,
                decimal_odds=row.decimal_odds,
                observed_at=row.observed_at,
                provider_timestamp=row.provider_timestamp,
            )
            for row in rows
        ),
    )


def get_market_baseline_view(
    *,
    event_id: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
) -> MarketBaselineResponse:
    dataset = build_market_baseline(
        event_id=event_id,
        decision_as_of=decision_as_of,
        paths=paths,
        persist=False,
    )
    return MarketBaselineResponse(
        event_id=event_id,
        as_of=decision_as_of,
        records=dataset.records,
    )


def get_market_analysis_view(
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
) -> MarketAnalysisResponse:
    records = analyze_market(
        event_id=event_id,
        decision_as_of=decision_as_of,
        model_probabilities=model_probabilities,
        payout_cost_rule_version=payout_cost_rule_version,
        uncertainty=uncertainty,
        data_quality=data_quality,
        model_validated=model_validated,
        data_conflict=data_conflict,
        paths=paths,
    )
    return MarketAnalysisResponse(
        event_id=event_id,
        as_of=decision_as_of,
        records=records,
    )


def get_model_view(
    *,
    model_id: str,
    model_version: str,
    paths: ProjectPaths | None = None,
) -> ModelLookupResponse:
    record = get_model_registry_record(
        model_id=model_id,
        model_version=model_version,
        paths=paths,
    )
    return ModelLookupResponse(found=record is not None, model=record)


def get_backtest_view(
    *,
    backtest_id: str,
    paths: ProjectPaths | None = None,
) -> BacktestLookupResponse:
    record = get_backtest_record(backtest_id=backtest_id, paths=paths)
    return BacktestLookupResponse(found=record is not None, backtest=record)


def get_canonical_entities_view(
    *,
    entity_kind: str,
    sport: str | None = None,
    entity_id_prefix: str | None = None,
    paths: ProjectPaths | None = None,
) -> CanonicalEntityListResponse:
    records = list_canonical_entities(
        entity_kind=entity_kind,
        sport=sport,
        entity_id_prefix=entity_id_prefix,
        paths=paths,
    )
    return CanonicalEntityListResponse(
        entity_kind=entity_kind,
        sport=sport,
        entity_id_prefix=entity_id_prefix,
        records=records,
    )


def get_entity_proposals_view(
    *,
    provider_id: str,
    status: str | None = None,
    paths: ProjectPaths | None = None,
) -> EntityProposalListResponse:
    records = list_entity_proposals(
        provider_id=provider_id,
        status=status,
        paths=paths,
    )
    return EntityProposalListResponse(
        provider_id=provider_id,
        status=status,
        records=records,
    )


def get_mapping_review_summary_view(
    *,
    provider_id: str,
    entity_kind: str,
    paths: ProjectPaths | None = None,
) -> ProviderMappingReviewSummary:
    return get_mapping_review_summary(
        provider_id=provider_id,
        entity_kind=entity_kind,
        paths=paths,
    )


def get_provider_usage_view(
    *,
    provider_id: str,
    paths: ProjectPaths | None = None,
) -> ProviderUsageResponse:
    usage = get_latest_provider_usage(provider_id=provider_id, paths=paths)
    return ProviderUsageResponse(found=usage is not None, usage=usage)


def get_forward_collection_status_view(
    *,
    provider_id: str,
    paths: ProjectPaths | None = None,
) -> ForwardCollectionStatusRecord:
    if provider_id != PROVIDER_ID:
        raise ValueError("forward collection status currently supports The Odds API only")
    effective_paths = paths or ProjectPaths.discover()
    settings = Settings(project_root=effective_paths.root)
    return get_forward_collection_status(
        paths=effective_paths,
        current_min_interval_minutes=settings.forward_current_min_interval_minutes,
        scores_min_interval_minutes=settings.forward_scores_min_interval_minutes,
    )


def get_nba_research_readiness_view(
    *,
    paths: ProjectPaths | None = None,
) -> ResearchReadinessStatusRecord:
    return get_nba_research_readiness_status(paths=paths, refresh=False)


def get_operational_status_view(
    *,
    paths: ProjectPaths | None = None,
) -> OperationalMonitorSnapshotRecord:
    return get_operational_status(paths=paths, refresh=False)


def get_event_result_view(
    *,
    event_id: str,
    paths: ProjectPaths | None = None,
) -> EventResultResponse:
    result = get_latest_event_result(event_id=event_id, paths=paths)
    return EventResultResponse(found=result is not None, result=result)


def get_paper_portfolio_view(
    *,
    paths: ProjectPaths | None = None,
) -> PaperPortfolioResponse:
    trades = list_paper_trades(paths=paths)
    settlements = list_settlements(paths=paths)
    open_count = sum(1 for trade in trades if trade.status == "OPEN")
    settled_count = sum(1 for settlement in settlements if settlement.settlement_status != "VOID")
    void_count = sum(1 for settlement in settlements if settlement.settlement_status == "VOID")
    return PaperPortfolioResponse(
        open_count=open_count,
        settled_count=settled_count,
        void_count=void_count,
        total_stake=sum(trade.stake for trade in trades),
        realized_pnl=sum(settlement.pnl for settlement in settlements),
        trades=trades,
        settlements=settlements,
    )
