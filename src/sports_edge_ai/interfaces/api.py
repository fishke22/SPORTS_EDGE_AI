from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

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
from sports_edge_ai.common.root import ProjectPaths
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

logger = logging.getLogger(__name__)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    model_probabilities: dict[str, float]
    payout_cost_rule_version: str = "synthetic-zero-cost-v1"
    uncertainty: float = Field(default=0.10, ge=0.0, le=1.0)
    data_quality: DataQualityStatus = DataQualityStatus.GREEN
    is_model_validated: bool = False
    data_conflict: bool = False


def create_app(
    *,
    paths: ProjectPaths | None = None,
    serve_frontend: bool = True,
) -> FastAPI:
    effective_paths = paths or ProjectPaths.discover()
    app = FastAPI(
        title="SPORTS_EDGE_AI API",
        version="0.1.0",
        description="Portable sports-market research API. No automatic betting.",
    )

    @app.exception_handler(ValueError)
    async def handle_value_error(_request: Request, exc: ValueError) -> JSONResponse:
        logger.info("request validation failed: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def handle_missing_file(
        _request: Request,
        exc: FileNotFoundError,
    ) -> JSONResponse:
        logger.info("requested local resource missing: %s", exc)
        return JSONResponse(status_code=404, content={"detail": "resource not found"})

    @app.get("/api/v1/health", response_model=SystemHealth)
    def health() -> SystemHealth:
        return get_system_health(paths=effective_paths)

    @app.get("/api/v1/events/{event_id}/odds", response_model=OddsAsOfResponse)
    def odds_as_of(
        event_id: str,
        as_of: Annotated[datetime, Query()],
    ) -> OddsAsOfResponse:
        return get_odds_as_of(
            event_id=event_id,
            decision_as_of=as_of,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/events/{event_id}/market-baseline",
        response_model=MarketBaselineResponse,
    )
    def market_baseline(
        event_id: str,
        as_of: Annotated[datetime, Query()],
    ) -> MarketBaselineResponse:
        return get_market_baseline_view(
            event_id=event_id,
            decision_as_of=as_of,
            paths=effective_paths,
        )

    @app.post(
        "/api/v1/events/{event_id}/analysis",
        response_model=MarketAnalysisResponse,
    )
    def market_analysis(
        event_id: str,
        request: AnalysisRequest,
    ) -> MarketAnalysisResponse:
        return get_market_analysis_view(
            event_id=event_id,
            decision_as_of=request.as_of,
            model_probabilities=request.model_probabilities,
            payout_cost_rule_version=request.payout_cost_rule_version,
            uncertainty=request.uncertainty,
            data_quality=request.data_quality,
            model_validated=request.is_model_validated,
            data_conflict=request.data_conflict,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/models/{model_id}/{model_version}",
        response_model=ModelLookupResponse,
    )
    def model_lookup(model_id: str, model_version: str) -> ModelLookupResponse:
        result = get_model_view(
            model_id=model_id,
            model_version=model_version,
            paths=effective_paths,
        )
        if not result.found:
            raise HTTPException(status_code=404, detail="model not found")
        return result

    @app.get(
        "/api/v1/backtests/{backtest_id}",
        response_model=BacktestLookupResponse,
    )
    def backtest_lookup(backtest_id: str) -> BacktestLookupResponse:
        result = get_backtest_view(backtest_id=backtest_id, paths=effective_paths)
        if not result.found:
            raise HTTPException(status_code=404, detail="backtest not found")
        return result

    @app.get(
        "/api/v1/entities",
        response_model=CanonicalEntityListResponse,
    )
    def canonical_entities(
        entity_kind: Annotated[str, Query()],
        sport: Annotated[str | None, Query()] = None,
        entity_id_prefix: Annotated[str | None, Query()] = None,
    ) -> CanonicalEntityListResponse:
        return get_canonical_entities_view(
            entity_kind=entity_kind,
            sport=sport,
            entity_id_prefix=entity_id_prefix,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/providers/{provider_id}/entity-proposals",
        response_model=EntityProposalListResponse,
    )
    def entity_proposals(
        provider_id: str,
        status: Annotated[str | None, Query()] = None,
    ) -> EntityProposalListResponse:
        return get_entity_proposals_view(
            provider_id=provider_id,
            status=status,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/providers/{provider_id}/mapping-summary/{entity_kind}",
        response_model=ProviderMappingReviewSummary,
    )
    def mapping_summary(
        provider_id: str,
        entity_kind: str,
    ) -> ProviderMappingReviewSummary:
        return get_mapping_review_summary_view(
            provider_id=provider_id,
            entity_kind=entity_kind,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/providers/{provider_id}/usage",
        response_model=ProviderUsageResponse,
    )
    def provider_usage(provider_id: str) -> ProviderUsageResponse:
        return get_provider_usage_view(
            provider_id=provider_id,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/providers/{provider_id}/collection-status",
        response_model=ForwardCollectionStatusRecord,
    )
    def collection_status(provider_id: str) -> ForwardCollectionStatusRecord:
        return get_forward_collection_status_view(
            provider_id=provider_id,
            paths=effective_paths,
        )

    @app.get(
        "/api/v1/research/nba/readiness",
        response_model=ResearchReadinessStatusRecord,
    )
    def nba_research_readiness() -> ResearchReadinessStatusRecord:
        return get_nba_research_readiness_view(paths=effective_paths)

    @app.get(
        "/api/v1/operations/status",
        response_model=OperationalMonitorSnapshotRecord,
    )
    def operational_status() -> OperationalMonitorSnapshotRecord:
        return get_operational_status_view(paths=effective_paths)

    @app.get(
        "/api/v1/events/{event_id}/result",
        response_model=EventResultResponse,
    )
    def event_result(event_id: str) -> EventResultResponse:
        return get_event_result_view(event_id=event_id, paths=effective_paths)

    @app.get(
        "/api/v1/paper/portfolio",
        response_model=PaperPortfolioResponse,
    )
    def paper_portfolio() -> PaperPortfolioResponse:
        return get_paper_portfolio_view(paths=effective_paths)

    frontend_dist = effective_paths.root / "frontend" / "dist"
    if serve_frontend and frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )

    return app


app = create_app()


def main() -> None:
    configure_logging()
    uvicorn.run(
        "sports_edge_ai.interfaces.api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
