from __future__ import annotations

import json

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    CanonicalEvent,
    CanonicalMarket,
    DataQualityRecord,
    OddsSnapshot,
)
from sports_edge_ai.infrastructure.bronze import BronzeObject
from sports_edge_ai.infrastructure.db import connect, migrate


def persist_raw_provider_ingestion(
    *,
    paths: ProjectPaths,
    bronze: BronzeObject,
    schema_version: str,
    row_count: int,
) -> None:
    if row_count < 0:
        raise ValueError("row_count must be non-negative")
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
                row_count,
                bronze.manifest_relative_path,
                True,
                None,
            ],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def persist_provider_ingestion(
    *,
    paths: ProjectPaths,
    bronze: BronzeObject,
    schema_version: str,
    events: tuple[CanonicalEvent, ...],
    markets: tuple[CanonicalMarket, ...],
    odds: tuple[OddsSnapshot, ...],
    data_quality: DataQualityRecord,
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
        for event in events:
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
        connection.execute(
            "INSERT OR REPLACE INTO data_quality VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                data_quality.data_quality_id,
                data_quality.provider,
                data_quality.observed_at,
                data_quality.status,
                data_quality.freshness_seconds,
                data_quality.missing_rate,
                data_quality.duplicate_rate,
                data_quality.mapping_rate,
                data_quality.schema_version,
                data_quality.message,
            ],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
