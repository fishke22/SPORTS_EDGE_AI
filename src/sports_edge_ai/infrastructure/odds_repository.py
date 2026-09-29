from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect_readonly


@dataclass(frozen=True, slots=True)
class AsOfOdds:
    market_id: str
    bookmaker: str
    source: str
    decimal_odds: float
    observed_at: datetime
    provider_timestamp: datetime | None
    raw_source_ref: str
    payload_hash: str
    odds_snapshot_id: str | None = None


def get_event_odds_as_of(
    *,
    event_id: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
) -> tuple[AsOfOdds, ...]:
    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise ValueError("decision_as_of must be timezone-aware")

    connection = connect_readonly(paths)
    try:
        rows = connection.execute(
            """
            SELECT market_id, bookmaker, source, decimal_odds, observed_at,
                   provider_timestamp, raw_source_ref, payload_hash, odds_snapshot_id
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY market_id, bookmaker, source
                    ORDER BY observed_at DESC, ingested_at DESC
                ) AS row_rank
                FROM odds_snapshots
                WHERE event_id = ?
                  AND observed_at <= ?
                  AND (provider_timestamp IS NULL OR provider_timestamp <= ?)
            ) ranked
            WHERE row_rank = 1
            ORDER BY market_id, bookmaker, source
            """,
            [event_id, decision_as_of, decision_as_of],
        ).fetchall()
    finally:
        connection.close()

    return tuple(
        AsOfOdds(
            market_id=row[0],
            bookmaker=row[1],
            source=row[2],
            decimal_odds=float(row[3]),
            observed_at=row[4],
            provider_timestamp=row[5],
            raw_source_ref=row[6],
            payload_hash=row[7],
            odds_snapshot_id=row[8],
        )
        for row in rows
    )


@dataclass(frozen=True, slots=True)
class MarketOddsAsOf:
    market_id: str
    market_type: str
    period: str
    selection: str
    bookmaker: str
    source: str
    decimal_odds: float
    observed_at: datetime
    provider_timestamp: datetime | None
    raw_source_ref: str
    payload_hash: str
    odds_snapshot_id: str | None = None


def get_event_market_odds_as_of(
    *,
    event_id: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
) -> tuple[MarketOddsAsOf, ...]:
    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise ValueError("decision_as_of must be timezone-aware")

    connection = connect_readonly(paths)
    try:
        rows = connection.execute(
            """
            SELECT ranked.market_id, markets.market_type, markets.period,
                   markets.selection, ranked.bookmaker, ranked.source,
                   ranked.decimal_odds, ranked.observed_at,
                   ranked.provider_timestamp, ranked.raw_source_ref,
                   ranked.payload_hash, ranked.odds_snapshot_id
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY market_id, bookmaker, source
                    ORDER BY observed_at DESC, ingested_at DESC
                ) AS row_rank
                FROM odds_snapshots
                WHERE event_id = ?
                  AND observed_at <= ?
                  AND (provider_timestamp IS NULL OR provider_timestamp <= ?)
            ) ranked
            JOIN canonical_markets markets
              ON markets.market_id = ranked.market_id
            WHERE ranked.row_rank = 1
            ORDER BY ranked.bookmaker, ranked.source, ranked.market_id
            """,
            [event_id, decision_as_of, decision_as_of],
        ).fetchall()
    finally:
        connection.close()

    return tuple(
        MarketOddsAsOf(
            market_id=row[0],
            market_type=row[1],
            period=row[2],
            selection=row[3],
            bookmaker=row[4],
            source=row[5],
            decimal_odds=float(row[6]),
            observed_at=row[7],
            provider_timestamp=row[8],
            raw_source_ref=row[9],
            payload_hash=row[10],
            odds_snapshot_id=row[11],
        )
        for row in rows
    )
