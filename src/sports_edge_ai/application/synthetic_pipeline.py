from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.frame_contracts import ODDS_SNAPSHOT_FRAME_SCHEMA
from sports_edge_ai.domain.schemas import CanonicalEvent, CanonicalMarket, OddsSnapshot
from sports_edge_ai.infrastructure.bronze import BronzeObject, write_bronze_payload
from sports_edge_ai.infrastructure.db import connect, migrate

SYNTHETIC_PROVIDER = "synthetic_nba"
SYNTHETIC_BOOKMAKER = "SYNTHETIC_BOOK"


@dataclass(frozen=True, slots=True)
class SyntheticIngestionResult:
    bronze: BronzeObject
    event: CanonicalEvent
    markets: tuple[CanonicalMarket, ...]
    odds: tuple[OddsSnapshot, ...]
    silver_paths: tuple[str, ...]


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("synthetic fixture datetime must be timezone-aware")
    return parsed


def _normalize(
    payload: dict[str, Any], bronze: BronzeObject
) -> tuple[CanonicalEvent, tuple[CanonicalMarket, ...], tuple[OddsSnapshot, ...]]:
    event_raw = payload["event"]
    market_raw = payload["market"]
    odds_raw = payload["odds"]
    if (
        not isinstance(event_raw, dict)
        or not isinstance(market_raw, dict)
        or not isinstance(odds_raw, dict)
    ):
        raise ValueError("synthetic fixture has invalid object structure")

    observed_at = _parse_dt(str(event_raw["observed_at"]))
    ingested_at = _parse_dt(str(event_raw["ingested_at"]))
    event_id = str(event_raw["event_id"])
    event = CanonicalEvent(
        event_id=event_id,
        sport=str(event_raw["sport"]),
        league=str(event_raw["league"]),
        home_team_id=str(event_raw["home_team_id"]),
        away_team_id=str(event_raw["away_team_id"]),
        scheduled_start=_parse_dt(str(event_raw["scheduled_start"])),
        source_event_ids={SYNTHETIC_PROVIDER: event_id},
        effective_at=observed_at,
        observed_at=observed_at,
        ingested_at=ingested_at,
    )

    markets: list[CanonicalMarket] = []
    odds: list[OddsSnapshot] = []
    base_market_id = str(market_raw["market_id"])
    for selection, decimal_odds in sorted(odds_raw.items()):
        selection_key = str(selection).upper()
        market_id = f"{base_market_id}:{selection_key}"
        market = CanonicalMarket(
            market_id=market_id,
            event_id=event_id,
            market_type=str(market_raw["market_type"]),
            period=str(market_raw.get("period", "FULL_GAME")),
            selection=selection_key,
        )
        snapshot_material = (
            f"{bronze.payload_sha256}|{market_id}|{observed_at.isoformat()}"
        ).encode()
        snapshot_id = hashlib.sha256(snapshot_material).hexdigest()
        snapshot = OddsSnapshot(
            odds_snapshot_id=snapshot_id,
            event_id=event_id,
            market_id=market_id,
            bookmaker=SYNTHETIC_BOOKMAKER,
            source=SYNTHETIC_PROVIDER,
            decimal_odds=float(decimal_odds),
            observed_at=observed_at,
            provider_timestamp=None,
            ingested_at=ingested_at,
            raw_source_ref=bronze.relative_path,
            payload_hash=bronze.payload_sha256,
        )
        markets.append(market)
        odds.append(snapshot)

    return event, tuple(markets), tuple(odds)


def _write_silver(
    *,
    paths: ProjectPaths,
    bronze: BronzeObject,
    event: CanonicalEvent,
    markets: tuple[CanonicalMarket, ...],
    odds: tuple[OddsSnapshot, ...],
) -> tuple[str, ...]:
    event_dir = paths.silver / "events"
    market_dir = paths.silver / "markets"
    odds_dir = paths.silver / "odds"
    for directory in (event_dir, market_dir, odds_dir):
        directory.mkdir(parents=True, exist_ok=True)

    event_path = event_dir / f"{bronze.ingest_run_id}.parquet"
    market_path = market_dir / f"{bronze.ingest_run_id}.parquet"
    odds_path = odds_dir / f"{bronze.ingest_run_id}.parquet"
    pl.DataFrame(
        [
            {
                **event.model_dump(exclude={"source_event_ids"}),
                "source_event_ids": json.dumps(event.source_event_ids, sort_keys=True),
            }
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


def _persist(
    *,
    paths: ProjectPaths,
    bronze: BronzeObject,
    schema_version: str,
    event: CanonicalEvent,
    markets: tuple[CanonicalMarket, ...],
    odds: tuple[OddsSnapshot, ...],
) -> None:
    migrate(paths)
    connection = connect(paths)
    try:
        connection.execute("BEGIN")
        connection.execute(
            "INSERT OR IGNORE INTO raw_objects VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                bronze.payload_sha256,
                bronze.provider,
                bronze.relative_path,
                "application/json",
                bronze.object_bytes,
                False,
                bronze.ingested_at,
            ],
        )
        connection.execute(
            "INSERT OR IGNORE INTO ingest_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                bronze.ingest_run_id,
                bronze.provider,
                bronze.observed_at,
                bronze.ingested_at,
                bronze.payload_sha256,
                schema_version,
                len(odds),
                bronze.manifest_relative_path,
                True,
                None,
            ],
        )
        connection.execute(
            "INSERT OR IGNORE INTO canonical_events VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                event.event_id,
                event.schema_version,
                event.sport,
                event.league,
                event.season,
                event.home_team_id,
                event.away_team_id,
                event.scheduled_start,
                event.venue_id,
                event.status,
                json.dumps(event.source_event_ids, sort_keys=True),
                event.effective_at,
                event.observed_at,
                event.ingested_at,
            ],
        )
        for market in markets:
            connection.execute(
                "INSERT OR IGNORE INTO canonical_markets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    market.market_id,
                    market.schema_version,
                    market.event_id,
                    market.market_type,
                    market.period,
                    market.selection,
                    market.line,
                    market.market_rules_version,
                ],
            )
        for snapshot in odds:
            connection.execute(
                "INSERT OR IGNORE INTO odds_snapshots VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    snapshot.odds_snapshot_id,
                    snapshot.schema_version,
                    snapshot.event_id,
                    snapshot.market_id,
                    snapshot.bookmaker,
                    snapshot.source,
                    snapshot.decimal_odds,
                    snapshot.observed_at,
                    snapshot.provider_timestamp,
                    snapshot.ingested_at,
                    snapshot.is_live,
                    snapshot.is_closing,
                    snapshot.raw_source_ref,
                    snapshot.payload_hash,
                ],
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def ingest_synthetic_snapshot(
    fixture_path: Path,
    *,
    paths: ProjectPaths | None = None,
) -> SyntheticIngestionResult:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    raw_bytes = fixture_path.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("synthetic fixture must contain a JSON object")

    event_raw = payload.get("event")
    if not isinstance(event_raw, dict):
        raise ValueError("synthetic fixture must contain event object")
    observed_at = _parse_dt(str(event_raw["observed_at"]))
    ingested_at = _parse_dt(str(event_raw["ingested_at"]))
    schema_version = str(payload.get("schema_version", "synthetic-market-v1"))
    bronze = write_bronze_payload(
        paths=effective_paths,
        provider=SYNTHETIC_PROVIDER,
        payload=raw_bytes,
        observed_at=observed_at,
        ingested_at=ingested_at,
        schema_version=schema_version,
    )
    event, markets, odds = _normalize(payload, bronze)
    silver_paths = _write_silver(
        paths=effective_paths,
        bronze=bronze,
        event=event,
        markets=markets,
        odds=odds,
    )
    _persist(
        paths=effective_paths,
        bronze=bronze,
        schema_version=schema_version,
        event=event,
        markets=markets,
        odds=odds,
    )
    return SyntheticIngestionResult(bronze, event, markets, odds, silver_paths)
