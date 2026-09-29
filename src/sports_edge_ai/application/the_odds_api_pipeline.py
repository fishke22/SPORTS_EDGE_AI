from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.frame_contracts import ODDS_SNAPSHOT_FRAME_SCHEMA
from sports_edge_ai.domain.schemas import (
    CanonicalEvent,
    CanonicalMarket,
    DataQualityRecord,
    DataQualityStatus,
    OddsSnapshot,
)
from sports_edge_ai.infrastructure.ingestion_repository import persist_provider_ingestion
from sports_edge_ai.infrastructure.provider_repository import get_canonical_entity_id
from sports_edge_ai.infrastructure.providers.the_odds_api import (
    PROVIDER_ID,
    PROVIDER_SLUG,
    HistoricalOddsFetchResult,
)

SCHEMA_VERSION = "the-odds-api-historical-v4"


@dataclass(frozen=True, slots=True)
class TheOddsApiNormalizationResult:
    events: tuple[CanonicalEvent, ...]
    markets: tuple[CanonicalMarket, ...]
    odds: tuple[OddsSnapshot, ...]
    data_quality: DataQualityRecord
    silver_paths: tuple[str, ...]
    unresolved_entities: tuple[str, ...]


def canonical_nba_event_id(
    *,
    home_team_id: str,
    away_team_id: str,
    scheduled_start: datetime,
) -> str:
    material = (
        f"NBA|{home_team_id}|{away_team_id}|{scheduled_start.astimezone(UTC).isoformat()}"
    ).encode()
    return f"NBA_{hashlib.sha256(material).hexdigest()[:24]}"


def write_provider_silver(
    *,
    paths: ProjectPaths,
    ingest_run_id: str,
    events: tuple[CanonicalEvent, ...],
    markets: tuple[CanonicalMarket, ...],
    odds: tuple[OddsSnapshot, ...],
) -> tuple[str, ...]:
    if not events:
        return ()
    event_dir = paths.silver / "events"
    market_dir = paths.silver / "markets"
    odds_dir = paths.silver / "odds"
    for directory in (event_dir, market_dir, odds_dir):
        directory.mkdir(parents=True, exist_ok=True)
    event_path = event_dir / f"{ingest_run_id}.parquet"
    market_path = market_dir / f"{ingest_run_id}.parquet"
    odds_path = odds_dir / f"{ingest_run_id}.parquet"
    pl.DataFrame(
        [
            {
                **event.model_dump(exclude={"source_event_ids"}),
                "source_event_ids": json.dumps(event.source_event_ids, sort_keys=True),
            }
            for event in events
        ]
    ).write_parquet(event_path)
    pl.DataFrame([market.model_dump() for market in markets]).write_parquet(market_path)
    odds_frame = pl.DataFrame(
        [
            snapshot.model_dump(
                exclude={"odds_snapshot_id", "schema_version", "provider_timestamp"}
            )
            for snapshot in odds
        ]
    )
    ODDS_SNAPSHOT_FRAME_SCHEMA.validate(odds_frame)
    odds_frame.write_parquet(odds_path)
    return tuple(
        path.relative_to(paths.root).as_posix() for path in (event_path, market_path, odds_path)
    )


def normalize_historical_nba_h2h(
    fetch: HistoricalOddsFetchResult,
    *,
    paths: ProjectPaths | None = None,
) -> TheOddsApiNormalizationResult:
    effective_paths = paths or ProjectPaths.discover()
    requested_at = fetch.requested_at
    snapshot_time = fetch.snapshot.timestamp
    unresolved: set[str] = set()
    mappings: dict[str, str] = {}
    unique_names = {
        name for event in fetch.snapshot.data for name in (event.home_team, event.away_team)
    }
    for name in sorted(unique_names):
        canonical = get_canonical_entity_id(
            provider_id=PROVIDER_ID,
            entity_kind="TEAM",
            provider_entity_id=name,
            paths=effective_paths,
        )
        if canonical is None:
            unresolved.add(name)
        else:
            mappings[name] = canonical

    mapping_rate = 1.0 if not unique_names else len(mappings) / len(unique_names)
    freshness_seconds = max(0, int((requested_at - snapshot_time).total_seconds()))
    quality_id = hashlib.sha256(
        f"{PROVIDER_SLUG}|{fetch.bronze.payload_sha256}".encode()
    ).hexdigest()
    if unresolved:
        quality = DataQualityRecord(
            data_quality_id=quality_id,
            provider=PROVIDER_SLUG,
            observed_at=snapshot_time,
            status=DataQualityStatus.RED,
            freshness_seconds=freshness_seconds,
            missing_rate=0.0,
            duplicate_rate=0.0,
            mapping_rate=mapping_rate,
            schema_version="the-odds-api-dq-v1",
            message="unresolved TEAM mappings: " + ", ".join(sorted(unresolved)),
        )
        persist_provider_ingestion(
            paths=effective_paths,
            bronze=fetch.bronze,
            schema_version=SCHEMA_VERSION,
            events=(),
            markets=(),
            odds=(),
            data_quality=quality,
        )
        return TheOddsApiNormalizationResult((), (), (), quality, (), tuple(sorted(unresolved)))

    events: list[CanonicalEvent] = []
    markets_by_id: dict[str, CanonicalMarket] = {}
    odds: list[OddsSnapshot] = []
    for raw_event in fetch.snapshot.data:
        if raw_event.commence_time <= requested_at:
            continue
        home_id = mappings[raw_event.home_team]
        away_id = mappings[raw_event.away_team]
        event_id = canonical_nba_event_id(
            home_team_id=home_id,
            away_team_id=away_id,
            scheduled_start=raw_event.commence_time,
        )
        events.append(
            CanonicalEvent(
                event_id=event_id,
                sport="NBA",
                league="NBA",
                home_team_id=home_id,
                away_team_id=away_id,
                scheduled_start=raw_event.commence_time,
                source_event_ids={PROVIDER_SLUG: raw_event.id},
                effective_at=snapshot_time,
                observed_at=snapshot_time,
                ingested_at=fetch.bronze.ingested_at,
            )
        )
        for bookmaker in raw_event.bookmakers:
            for market in bookmaker.markets:
                if market.key != "h2h":
                    continue
                names = {outcome.name for outcome in market.outcomes}
                expected = {raw_event.home_team, raw_event.away_team}
                if len(market.outcomes) != 2 or names != expected:
                    raise ValueError("NBA h2h outcomes must match home and away teams exactly")
                provider_timestamp = market.last_update or bookmaker.last_update or snapshot_time
                if provider_timestamp > requested_at:
                    raise RuntimeError("provider market timestamp exceeds requested_at")
                observed_at = max(snapshot_time, provider_timestamp)
                for outcome in market.outcomes:
                    selection = "HOME" if outcome.name == raw_event.home_team else "AWAY"
                    market_id = f"{event_id}:H2H:{selection}"
                    markets_by_id.setdefault(
                        market_id,
                        CanonicalMarket(
                            market_id=market_id,
                            event_id=event_id,
                            market_type="MONEYLINE",
                            period="FULL_GAME",
                            selection=selection,
                            market_rules_version="the-odds-api-h2h-v1",
                        ),
                    )
                    snapshot_material = (
                        f"{fetch.bronze.payload_sha256}|{market_id}|{bookmaker.key}|"
                        f"{observed_at.isoformat()}|{outcome.price}"
                    ).encode()
                    odds.append(
                        OddsSnapshot(
                            odds_snapshot_id=hashlib.sha256(snapshot_material).hexdigest(),
                            event_id=event_id,
                            market_id=market_id,
                            bookmaker=bookmaker.key,
                            source=PROVIDER_SLUG,
                            decimal_odds=outcome.price,
                            observed_at=observed_at,
                            provider_timestamp=provider_timestamp,
                            ingested_at=fetch.bronze.ingested_at,
                            is_live=False,
                            is_closing=False,
                            raw_source_ref=fetch.bronze.relative_path,
                            payload_hash=fetch.bronze.payload_sha256,
                        )
                    )

    quality = DataQualityRecord(
        data_quality_id=quality_id,
        provider=PROVIDER_SLUG,
        observed_at=snapshot_time,
        status=DataQualityStatus.GREEN if odds else DataQualityStatus.YELLOW,
        freshness_seconds=freshness_seconds,
        missing_rate=0.0 if odds else 1.0,
        duplicate_rate=0.0,
        mapping_rate=mapping_rate,
        schema_version="the-odds-api-dq-v1",
        message=None if odds else "no pregame NBA h2h odds in snapshot",
    )
    event_tuple = tuple(events)
    market_tuple = tuple(markets_by_id.values())
    odds_tuple = tuple(odds)
    silver_paths = write_provider_silver(
        paths=effective_paths,
        ingest_run_id=fetch.bronze.ingest_run_id,
        events=event_tuple,
        markets=market_tuple,
        odds=odds_tuple,
    )
    persist_provider_ingestion(
        paths=effective_paths,
        bronze=fetch.bronze,
        schema_version=SCHEMA_VERSION,
        events=event_tuple,
        markets=market_tuple,
        odds=odds_tuple,
        data_quality=quality,
    )
    return TheOddsApiNormalizationResult(
        event_tuple,
        market_tuple,
        odds_tuple,
        quality,
        silver_paths,
        (),
    )
