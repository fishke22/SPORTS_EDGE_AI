from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from sports_edge_ai.domain.schemas import (
    BacktestRecord,
    CanonicalEntityRecord,
    EventResultRecord,
    MarketAnalysisRecord,
    MarketBaselineRecord,
    ModelRegistryRecord,
    PaperTradeRecord,
    ProviderEntityProposalRecord,
    ProviderUsageSnapshot,
    SettlementRecord,
)


class InterfaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SystemHealth(InterfaceModel):
    status: str
    database_ready: bool
    schema_version: str | None


class OddsAsOfItem(InterfaceModel):
    market_id: str
    bookmaker: str
    source: str
    decimal_odds: float
    observed_at: datetime
    provider_timestamp: datetime | None


class OddsAsOfResponse(InterfaceModel):
    event_id: str
    as_of: datetime
    odds: tuple[OddsAsOfItem, ...]


class MarketBaselineResponse(InterfaceModel):
    event_id: str
    as_of: datetime
    records: tuple[MarketBaselineRecord, ...]


class MarketAnalysisResponse(InterfaceModel):
    event_id: str
    as_of: datetime
    records: tuple[MarketAnalysisRecord, ...]


class ModelLookupResponse(InterfaceModel):
    found: bool
    model: ModelRegistryRecord | None = None


class BacktestLookupResponse(InterfaceModel):
    found: bool
    backtest: BacktestRecord | None = None


class CanonicalEntityListResponse(InterfaceModel):
    entity_kind: str
    sport: str | None = None
    entity_id_prefix: str | None = None
    records: tuple[CanonicalEntityRecord, ...]


class EntityProposalListResponse(InterfaceModel):
    provider_id: str
    status: str | None = None
    records: tuple[ProviderEntityProposalRecord, ...]


class ProviderUsageResponse(InterfaceModel):
    found: bool
    usage: ProviderUsageSnapshot | None = None


class EventResultResponse(InterfaceModel):
    found: bool
    result: EventResultRecord | None = None


class PaperPortfolioResponse(InterfaceModel):
    open_count: int
    settled_count: int
    void_count: int
    total_stake: float
    realized_pnl: float
    trades: tuple[PaperTradeRecord, ...]
    settlements: tuple[SettlementRecord, ...]
