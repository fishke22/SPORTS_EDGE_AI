from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, field_validator

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import ProviderUsageSnapshot
from sports_edge_ai.infrastructure.bronze import BronzeObject, write_bronze_payload
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.provider_repository import get_provider_access_policy
from sports_edge_ai.infrastructure.provider_usage_repository import (
    assert_credit_budget,
    persist_provider_usage,
    usage_snapshot_from_headers,
)
from sports_edge_ai.infrastructure.providers.the_odds_api import (
    PROVIDER_ID,
    PROVIDER_SLUG,
    HttpResponse,
    OddsApiEvent,
    OddsApiTransport,
    QuotaHeaders,
    UrllibOddsApiTransport,
)

CURRENT_NBA_ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
NBA_PARTICIPANTS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/participants"
NBA_SCORES_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/scores"


class FreeProviderModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class OddsApiParticipant(FreeProviderModel):
    id: str
    full_name: str


class OddsApiScoreItem(FreeProviderModel):
    name: str
    score: str


class OddsApiScoreEvent(FreeProviderModel):
    id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    completed: bool
    home_team: str
    away_team: str
    scores: tuple[OddsApiScoreItem, ...] | None = None
    last_update: datetime | None = None

    @field_validator("commence_time", "last_update")
    @classmethod
    def require_aware_times(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("score timestamps must be timezone-aware")
        return value


@dataclass(frozen=True, slots=True)
class CurrentOddsFetchResult:
    bronze: BronzeObject
    fetched_at: datetime
    events: tuple[OddsApiEvent, ...]
    quota: QuotaHeaders
    usage: ProviderUsageSnapshot


@dataclass(frozen=True, slots=True)
class ParticipantsFetchResult:
    bronze: BronzeObject
    fetched_at: datetime
    participants: tuple[OddsApiParticipant, ...]
    quota: QuotaHeaders
    usage: ProviderUsageSnapshot


@dataclass(frozen=True, slots=True)
class ScoresFetchResult:
    bronze: BronzeObject
    fetched_at: datetime
    events: tuple[OddsApiScoreEvent, ...]
    quota: QuotaHeaders
    usage: ProviderUsageSnapshot


def _optional_int(headers: dict[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _quota(response: HttpResponse) -> QuotaHeaders:
    return QuotaHeaders(
        remaining=_optional_int(response.headers, "x-requests-remaining"),
        used=_optional_int(response.headers, "x-requests-used"),
        last_cost=_optional_int(response.headers, "x-requests-last"),
    )


def _require_access(
    *,
    paths: ProjectPaths,
    local_monthly_budget: int,
    estimated_cost: int,
) -> None:
    migrate(paths)
    policy = get_provider_access_policy(provider_id=PROVIDER_ID, paths=paths)
    if not policy.enabled:
        raise RuntimeError("The Odds API provider is disabled in provider_registry")
    if policy.automated_access_allowed is not True:
        raise RuntimeError("provider policy does not permit automated access")
    if policy.redistribution_allowed is not False:
        raise RuntimeError("provider redistribution policy must remain fail-closed")
    assert_credit_budget(
        provider_id=PROVIDER_ID,
        local_monthly_budget=local_monthly_budget,
        estimated_cost=estimated_cost,
        paths=paths,
    )


def _finalize_usage(
    *,
    quota: QuotaHeaders,
    fetched_at: datetime,
    local_monthly_budget: int,
    endpoint_kind: str,
    paths: ProjectPaths,
) -> ProviderUsageSnapshot:
    usage = usage_snapshot_from_headers(
        provider_id=PROVIDER_ID,
        observed_at=fetched_at,
        requests_remaining=quota.remaining,
        requests_used=quota.used,
        requests_last=quota.last_cost,
        local_monthly_budget=local_monthly_budget,
        endpoint_kind=endpoint_kind,
    )
    persist_provider_usage(usage, paths=paths)
    return usage


def _request(
    *,
    url: str,
    timeout_seconds: float,
    transport: OddsApiTransport | None,
) -> HttpResponse:
    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    return (transport or UrllibOddsApiTransport()).get(
        url=url,
        timeout_seconds=timeout_seconds,
    )


def _normalize_key(api_key: str) -> str:
    normalized = api_key.strip()
    if not normalized:
        raise ValueError("The Odds API key is required")
    return normalized


def fetch_current_nba_h2h(
    *,
    api_key: str,
    paths: ProjectPaths | None = None,
    fetched_at: datetime | None = None,
    region: str = "us",
    local_monthly_budget: int = 450,
    timeout_seconds: float = 20.0,
    transport: OddsApiTransport | None = None,
) -> CurrentOddsFetchResult:
    key = _normalize_key(api_key)
    if not region or "," in region:
        raise ValueError("free current-odds profile accepts exactly one region")
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    actual_fetched_at = fetched_at or datetime.now(UTC)
    if actual_fetched_at.tzinfo is None or actual_fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")
    _require_access(
        paths=effective_paths,
        local_monthly_budget=local_monthly_budget,
        estimated_cost=1,
    )
    query = urlencode(
        {
            "apiKey": key,
            "regions": region,
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
    )
    response = _request(
        url=f"{CURRENT_NBA_ODDS_URL}?{query}",
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    decoded = json.loads(response.body.decode("utf-8"))
    events = tuple(OddsApiEvent.model_validate(item) for item in decoded)
    if any(event.sport_key != "basketball_nba" for event in events):
        raise ValueError("current NBA response contains a non-NBA sport key")
    bronze = write_bronze_payload(
        paths=effective_paths,
        provider=PROVIDER_SLUG,
        payload=response.body,
        observed_at=actual_fetched_at,
        ingested_at=actual_fetched_at,
        schema_version="the-odds-api-current-v4",
    )
    quota = _quota(response)
    usage = _finalize_usage(
        quota=quota,
        fetched_at=actual_fetched_at,
        local_monthly_budget=local_monthly_budget,
        endpoint_kind="current_nba_h2h",
        paths=effective_paths,
    )
    return CurrentOddsFetchResult(bronze, actual_fetched_at, events, quota, usage)


def fetch_nba_participants(
    *,
    api_key: str,
    paths: ProjectPaths | None = None,
    fetched_at: datetime | None = None,
    local_monthly_budget: int = 450,
    timeout_seconds: float = 20.0,
    transport: OddsApiTransport | None = None,
) -> ParticipantsFetchResult:
    key = _normalize_key(api_key)
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    actual_fetched_at = fetched_at or datetime.now(UTC)
    if actual_fetched_at.tzinfo is None or actual_fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")
    _require_access(
        paths=effective_paths,
        local_monthly_budget=local_monthly_budget,
        estimated_cost=1,
    )
    response = _request(
        url=f"{NBA_PARTICIPANTS_URL}?{urlencode({'apiKey': key})}",
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    decoded = json.loads(response.body.decode("utf-8"))
    participants = tuple(OddsApiParticipant.model_validate(item) for item in decoded)
    names = [participant.full_name for participant in participants]
    if len(names) != len(set(names)):
        raise ValueError("participant response contains duplicate full_name values")
    bronze = write_bronze_payload(
        paths=effective_paths,
        provider=PROVIDER_SLUG,
        payload=response.body,
        observed_at=actual_fetched_at,
        ingested_at=actual_fetched_at,
        schema_version="the-odds-api-participants-v4",
    )
    quota = _quota(response)
    usage = _finalize_usage(
        quota=quota,
        fetched_at=actual_fetched_at,
        local_monthly_budget=local_monthly_budget,
        endpoint_kind="nba_participants",
        paths=effective_paths,
    )
    return ParticipantsFetchResult(bronze, actual_fetched_at, participants, quota, usage)


def fetch_nba_scores(
    *,
    api_key: str,
    paths: ProjectPaths | None = None,
    fetched_at: datetime | None = None,
    days_from: int = 3,
    local_monthly_budget: int = 450,
    timeout_seconds: float = 20.0,
    transport: OddsApiTransport | None = None,
) -> ScoresFetchResult:
    key = _normalize_key(api_key)
    if days_from not in {1, 2, 3}:
        raise ValueError("days_from must be 1, 2, or 3")
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    actual_fetched_at = fetched_at or datetime.now(UTC)
    if actual_fetched_at.tzinfo is None or actual_fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")
    _require_access(
        paths=effective_paths,
        local_monthly_budget=local_monthly_budget,
        estimated_cost=2,
    )
    query = urlencode(
        {
            "apiKey": key,
            "daysFrom": days_from,
            "dateFormat": "iso",
        }
    )
    response = _request(
        url=f"{NBA_SCORES_URL}?{query}",
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    decoded = json.loads(response.body.decode("utf-8"))
    events = tuple(OddsApiScoreEvent.model_validate(item) for item in decoded)
    if any(event.sport_key != "basketball_nba" for event in events):
        raise ValueError("NBA scores response contains a non-NBA sport key")
    bronze = write_bronze_payload(
        paths=effective_paths,
        provider=PROVIDER_SLUG,
        payload=response.body,
        observed_at=actual_fetched_at,
        ingested_at=actual_fetched_at,
        schema_version="the-odds-api-scores-v4",
    )
    quota = _quota(response)
    usage = _finalize_usage(
        quota=quota,
        fetched_at=actual_fetched_at,
        local_monthly_budget=local_monthly_budget,
        endpoint_kind="nba_scores",
        paths=effective_paths,
    )
    return ScoresFetchResult(bronze, actual_fetched_at, events, quota, usage)
