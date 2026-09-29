from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.bronze import BronzeObject, write_bronze_payload
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.provider_repository import get_provider_access_policy

PROVIDER_ID = "provider_the_odds_api"
PROVIDER_SLUG = "the_odds_api"
HISTORICAL_NBA_ODDS_URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds"


class OddsApiProviderModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class OddsApiOutcome(OddsApiProviderModel):
    name: str
    price: float = Field(gt=1.0)


class OddsApiMarket(OddsApiProviderModel):
    key: str
    last_update: datetime | None = None
    outcomes: tuple[OddsApiOutcome, ...]

    @field_validator("last_update")
    @classmethod
    def require_aware_last_update(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("market last_update must be timezone-aware")
        return value


class OddsApiBookmaker(OddsApiProviderModel):
    key: str
    title: str
    last_update: datetime | None = None
    markets: tuple[OddsApiMarket, ...]

    @field_validator("last_update")
    @classmethod
    def require_aware_last_update(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("bookmaker last_update must be timezone-aware")
        return value


class OddsApiEvent(OddsApiProviderModel):
    id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: tuple[OddsApiBookmaker, ...]

    @field_validator("commence_time")
    @classmethod
    def require_aware_commence_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("commence_time must be timezone-aware")
        return value


class HistoricalOddsEnvelope(OddsApiProviderModel):
    timestamp: datetime
    previous_timestamp: datetime | None = None
    next_timestamp: datetime | None = None
    data: tuple[OddsApiEvent, ...]

    @field_validator("timestamp", "previous_timestamp", "next_timestamp")
    @classmethod
    def require_aware_snapshot_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("historical snapshot timestamps must be timezone-aware")
        return value


@dataclass(frozen=True, slots=True)
class HttpResponse:
    body: bytes
    headers: dict[str, str]


class OddsApiTransport(Protocol):
    def get(self, *, url: str, timeout_seconds: float) -> HttpResponse: ...


class ProviderRequestError(RuntimeError):
    pass


class UrllibOddsApiTransport:
    def get(self, *, url: str, timeout_seconds: float) -> HttpResponse:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "SPORTS_EDGE_AI/0.1",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read()
                headers = {key.lower(): value for key, value in response.headers.items()}
                return HttpResponse(body=body, headers=headers)
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            suffix = f"; retry_after={retry_after}" if retry_after else ""
            raise ProviderRequestError(
                f"The Odds API request failed with HTTP {exc.code}{suffix}"
            ) from None
        except URLError:
            raise ProviderRequestError("The Odds API transport failed") from None


@dataclass(frozen=True, slots=True)
class QuotaHeaders:
    remaining: int | None
    used: int | None
    last_cost: int | None


@dataclass(frozen=True, slots=True)
class HistoricalOddsFetchResult:
    bronze: BronzeObject
    requested_at: datetime
    snapshot: HistoricalOddsEnvelope
    quota: QuotaHeaders


def _optional_int(headers: dict[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_historical_odds_payload(
    payload: bytes,
    *,
    requested_at: datetime,
) -> HistoricalOddsEnvelope:
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("requested_at must be timezone-aware")
    decoded = json.loads(payload.decode("utf-8"))
    snapshot = HistoricalOddsEnvelope.model_validate(decoded)
    if snapshot.timestamp > requested_at:
        raise RuntimeError("provider snapshot timestamp exceeds requested_at")
    if any(event.sport_key != "basketball_nba" for event in snapshot.data):
        raise ValueError("historical NBA response contains a non-NBA sport key")
    return snapshot


def fetch_historical_nba_h2h_snapshot(
    *,
    api_key: str,
    requested_at: datetime,
    paths: ProjectPaths | None = None,
    ingested_at: datetime | None = None,
    region: str = "us",
    timeout_seconds: float = 20.0,
    transport: OddsApiTransport | None = None,
) -> HistoricalOddsFetchResult:
    normalized_api_key = api_key.strip()
    if not normalized_api_key:
        raise ValueError("The Odds API key is required")
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("requested_at must be timezone-aware")
    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    if not region or "," in region:
        raise ValueError("Phase 5 connector accepts exactly one region per request")

    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    policy = get_provider_access_policy(provider_id=PROVIDER_ID, paths=effective_paths)
    if not policy.enabled:
        raise RuntimeError("The Odds API provider is disabled in provider_registry")
    if policy.automated_access_allowed is not True:
        raise RuntimeError("provider policy does not permit automated access")
    if policy.redistribution_allowed is not False:
        raise RuntimeError("provider redistribution policy must be explicitly fail-closed")

    request_time = requested_at.astimezone(UTC)
    query = urlencode(
        {
            "apiKey": normalized_api_key,
            "regions": region,
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "date": request_time.isoformat().replace("+00:00", "Z"),
        }
    )
    response = (transport or UrllibOddsApiTransport()).get(
        url=f"{HISTORICAL_NBA_ODDS_URL}?{query}",
        timeout_seconds=timeout_seconds,
    )
    snapshot = parse_historical_odds_payload(
        response.body,
        requested_at=requested_at,
    )
    actual_ingested_at = ingested_at or datetime.now(UTC)
    bronze = write_bronze_payload(
        paths=effective_paths,
        provider=PROVIDER_SLUG,
        payload=response.body,
        observed_at=snapshot.timestamp,
        ingested_at=actual_ingested_at,
        schema_version="the-odds-api-historical-v4",
    )
    return HistoricalOddsFetchResult(
        bronze=bronze,
        requested_at=requested_at,
        snapshot=snapshot,
        quota=QuotaHeaders(
            remaining=_optional_int(response.headers, "x-requests-remaining"),
            used=_optional_int(response.headers, "x-requests-used"),
            last_cost=_optional_int(response.headers, "x-requests-last"),
        ),
    )
