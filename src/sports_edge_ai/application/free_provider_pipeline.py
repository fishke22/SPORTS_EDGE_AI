from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sports_edge_ai.application.entity_mapping import create_or_update_entity_proposal
from sports_edge_ai.application.the_odds_api_pipeline import (
    canonical_nba_event_id,
    write_provider_silver,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    CanonicalEvent,
    CanonicalMarket,
    DataQualityRecord,
    DataQualityStatus,
    EventResultRecord,
    OddsSnapshot,
    ProviderEntityProposalRecord,
)
from sports_edge_ai.infrastructure.ingestion_repository import (
    persist_provider_ingestion,
    persist_raw_provider_ingestion,
)
from sports_edge_ai.infrastructure.provider_repository import get_canonical_entity_id
from sports_edge_ai.infrastructure.providers.the_odds_api import PROVIDER_ID, PROVIDER_SLUG
from sports_edge_ai.infrastructure.providers.the_odds_api_free import (
    CurrentOddsFetchResult,
    ParticipantsFetchResult,
    ScoresFetchResult,
)
from sports_edge_ai.infrastructure.result_repository import (
    find_canonical_event_id_by_provider_event,
    persist_event_results,
)

CURRENT_SCHEMA_VERSION = "the-odds-api-current-v4"
PARTICIPANTS_SCHEMA_VERSION = "the-odds-api-participants-v4"
SCORES_SCHEMA_VERSION = "the-odds-api-scores-v4"


@dataclass(frozen=True, slots=True)
class FreeCurrentNormalizationResult:
    events: tuple[CanonicalEvent, ...]
    markets: tuple[CanonicalMarket, ...]
    odds: tuple[OddsSnapshot, ...]
    data_quality: DataQualityRecord
    silver_paths: tuple[str, ...]
    unresolved_entities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoresNormalizationResult:
    results: tuple[EventResultRecord, ...]
    unresolved_provider_events: tuple[str, ...]


def propose_nba_participant_mappings(
    fetch: ParticipantsFetchResult,
    *,
    paths: ProjectPaths | None = None,
) -> tuple[ProviderEntityProposalRecord, ...]:
    effective_paths = paths or ProjectPaths.discover()
    persist_raw_provider_ingestion(
        paths=effective_paths,
        bronze=fetch.bronze,
        schema_version=PARTICIPANTS_SCHEMA_VERSION,
        row_count=len(fetch.participants),
    )
    return tuple(
        create_or_update_entity_proposal(
            provider_id=PROVIDER_ID,
            entity_kind="TEAM",
            provider_entity_id=participant.full_name,
            provider_display_name=participant.full_name,
            provider_object_id=participant.id,
            observed_at=fetch.fetched_at,
            paths=effective_paths,
        )
        for participant in fetch.participants
    )


def normalize_current_nba_h2h(
    fetch: CurrentOddsFetchResult,
    *,
    paths: ProjectPaths | None = None,
) -> FreeCurrentNormalizationResult:
    effective_paths = paths or ProjectPaths.discover()
    unresolved: set[str] = set()
    mappings: dict[str, str] = {}
    unique_names = {name for event in fetch.events for name in (event.home_team, event.away_team)}
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
    quality_id = hashlib.sha256(
        f"{PROVIDER_SLUG}|current|{fetch.bronze.payload_sha256}".encode()
    ).hexdigest()
    if unresolved:
        quality = DataQualityRecord(
            data_quality_id=quality_id,
            provider=PROVIDER_SLUG,
            observed_at=fetch.fetched_at,
            status=DataQualityStatus.RED,
            freshness_seconds=0,
            missing_rate=0.0,
            duplicate_rate=0.0,
            mapping_rate=mapping_rate,
            schema_version="the-odds-api-current-dq-v1",
            message="unresolved TEAM mappings: " + ", ".join(sorted(unresolved)),
        )
        persist_provider_ingestion(
            paths=effective_paths,
            bronze=fetch.bronze,
            schema_version=CURRENT_SCHEMA_VERSION,
            events=(),
            markets=(),
            odds=(),
            data_quality=quality,
        )
        return FreeCurrentNormalizationResult((), (), (), quality, (), tuple(sorted(unresolved)))

    events: list[CanonicalEvent] = []
    markets_by_id: dict[str, CanonicalMarket] = {}
    odds: list[OddsSnapshot] = []
    for raw_event in fetch.events:
        if raw_event.commence_time <= fetch.fetched_at:
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
                effective_at=fetch.fetched_at,
                observed_at=fetch.fetched_at,
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
                provider_timestamp = market.last_update or bookmaker.last_update
                if provider_timestamp is not None and provider_timestamp > fetch.fetched_at:
                    raise RuntimeError("provider market timestamp exceeds fetched_at")
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
                    identity = (
                        f"{fetch.bronze.payload_sha256}|{market_id}|{bookmaker.key}|"
                        f"{fetch.fetched_at.isoformat()}|{outcome.price}"
                    ).encode()
                    odds.append(
                        OddsSnapshot(
                            odds_snapshot_id=hashlib.sha256(identity).hexdigest(),
                            event_id=event_id,
                            market_id=market_id,
                            bookmaker=bookmaker.key,
                            source=PROVIDER_SLUG,
                            decimal_odds=outcome.price,
                            observed_at=fetch.fetched_at,
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
        observed_at=fetch.fetched_at,
        status=DataQualityStatus.GREEN if odds else DataQualityStatus.YELLOW,
        freshness_seconds=0,
        missing_rate=0.0 if odds else 1.0,
        duplicate_rate=0.0,
        mapping_rate=mapping_rate,
        schema_version="the-odds-api-current-dq-v1",
        message=None if odds else "no pregame NBA h2h odds in current snapshot",
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
        schema_version=CURRENT_SCHEMA_VERSION,
        events=event_tuple,
        markets=market_tuple,
        odds=odds_tuple,
        data_quality=quality,
    )
    return FreeCurrentNormalizationResult(
        event_tuple,
        market_tuple,
        odds_tuple,
        quality,
        silver_paths,
        (),
    )


def normalize_nba_scores(
    fetch: ScoresFetchResult,
    *,
    paths: ProjectPaths | None = None,
) -> ScoresNormalizationResult:
    effective_paths = paths or ProjectPaths.discover()
    persist_raw_provider_ingestion(
        paths=effective_paths,
        bronze=fetch.bronze,
        schema_version=SCORES_SCHEMA_VERSION,
        row_count=len(fetch.events),
    )
    results: list[EventResultRecord] = []
    unresolved_events: list[str] = []
    for event in fetch.events:
        if not event.completed:
            continue
        if event.last_update is None:
            raise ValueError("completed score event requires last_update")
        if event.last_update > fetch.fetched_at:
            raise RuntimeError("provider score timestamp exceeds fetched_at")
        if event.scores is None or len(event.scores) != 2:
            raise ValueError("completed NBA score event requires two team scores")
        scores = {item.name: int(item.score) for item in event.scores}
        if set(scores) != {event.home_team, event.away_team}:
            raise ValueError("score team names must match home and away teams exactly")
        event_id = find_canonical_event_id_by_provider_event(
            provider_slug=PROVIDER_SLUG,
            provider_event_id=event.id,
            paths=effective_paths,
        )
        if event_id is None:
            unresolved_events.append(event.id)
        home_score = scores[event.home_team]
        away_score = scores[event.away_team]
        if home_score == away_score:
            result_outcome = "TIE"
        elif home_score > away_score:
            result_outcome = "HOME"
        else:
            result_outcome = "AWAY"
        identity = (
            f"{fetch.bronze.payload_sha256}|{event.id}|"
            f"{event.last_update.isoformat()}|{home_score}|{away_score}"
        ).encode()
        results.append(
            EventResultRecord(
                event_result_id=hashlib.sha256(identity).hexdigest(),
                event_id=event_id,
                provider_id=PROVIDER_ID,
                provider_event_id=event.id,
                home_score=home_score,
                away_score=away_score,
                result_outcome=result_outcome,
                completed=True,
                observed_at=fetch.fetched_at,
                provider_timestamp=event.last_update,
                raw_source_ref=fetch.bronze.relative_path,
                payload_hash=fetch.bronze.payload_sha256,
            )
        )
    result_tuple = tuple(results)
    persist_event_results(result_tuple, paths=effective_paths)
    return ScoresNormalizationResult(result_tuple, tuple(sorted(unresolved_events)))
