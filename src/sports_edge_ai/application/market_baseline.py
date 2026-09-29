from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from sports_edge_ai.application.pricing import (
    devig_multiplicative,
    fair_odds,
    gross_ev,
    implied_probability,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import MarketBaselineRecord
from sports_edge_ai.infrastructure.odds_repository import (
    MarketOddsAsOf,
    get_event_market_odds_as_of,
)


@dataclass(frozen=True, slots=True)
class MarketBaselineDataset:
    records: tuple[MarketBaselineRecord, ...]
    relative_path: str | None


def _market_group_id(market_id: str) -> str:
    if ":" not in market_id:
        raise ValueError("selection-level market_id must contain ':'")
    return market_id.rsplit(":", 1)[0]


def ensure_point_in_time(
    rows: tuple[MarketOddsAsOf, ...],
    decision_as_of: datetime,
) -> datetime:
    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise ValueError("decision_as_of must be timezone-aware")
    if not rows:
        raise ValueError("no odds are available at decision_as_of")

    max_observed_at = max(row.observed_at for row in rows)
    if max_observed_at > decision_as_of:
        raise RuntimeError("point-in-time violation: observed_at exceeds decision_as_of")
    if any(
        row.provider_timestamp is not None and row.provider_timestamp > decision_as_of
        for row in rows
    ):
        raise RuntimeError("point-in-time violation: provider_timestamp exceeds decision_as_of")
    return max_observed_at


def _group_rows(
    rows: tuple[MarketOddsAsOf, ...],
) -> dict[tuple[str, str, str], list[MarketOddsAsOf]]:
    grouped: dict[tuple[str, str, str], list[MarketOddsAsOf]] = defaultdict(list)
    for row in rows:
        grouped[(row.bookmaker, row.source, _market_group_id(row.market_id))].append(row)
    return grouped


def _build_records(
    *,
    event_id: str,
    rows: tuple[MarketOddsAsOf, ...],
    decision_as_of: datetime,
) -> tuple[MarketBaselineRecord, ...]:
    max_input_observed_at = ensure_point_in_time(rows, decision_as_of)
    records: list[MarketBaselineRecord] = []

    for (_, _, market_group_id), group in sorted(_group_rows(rows).items()):
        odds_by_selection = {row.selection: row.decimal_odds for row in group}
        if len(odds_by_selection) < 2:
            raise ValueError(f"market group {market_group_id} needs at least two selections")
        fair_probabilities = devig_multiplicative(odds_by_selection)

        for row in sorted(group, key=lambda item: item.selection):
            raw_probability = implied_probability(row.decimal_odds)
            fair_probability = fair_probabilities[row.selection]
            records.append(
                MarketBaselineRecord(
                    event_id=event_id,
                    market_group_id=market_group_id,
                    market_id=row.market_id,
                    market_type=row.market_type,
                    period=row.period,
                    selection=row.selection,
                    bookmaker=row.bookmaker,
                    source=row.source,
                    decimal_odds=row.decimal_odds,
                    market_probability_raw=raw_probability,
                    market_probability_fair=fair_probability,
                    fair_odds=fair_odds(fair_probability),
                    gross_ev_baseline=gross_ev(
                        fair_probability,
                        row.decimal_odds,
                    ),
                    decision_as_of=decision_as_of,
                    max_input_observed_at=max_input_observed_at,
                    payload_hash=row.payload_hash,
                    odds_snapshot_id=row.odds_snapshot_id,
                )
            )

    return tuple(records)


def _persist_records(
    *,
    paths: ProjectPaths,
    event_id: str,
    decision_as_of: datetime,
    records: tuple[MarketBaselineRecord, ...],
) -> str:
    as_of_utc = decision_as_of.astimezone(UTC)
    output_dir = (
        paths.gold
        / "market_baseline"
        / f"event_id={event_id}"
        / f"as_of={as_of_utc:%Y%m%dT%H%M%SZ}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "market_baseline.parquet"
    frame = pl.DataFrame([record.model_dump() for record in records])
    frame.write_parquet(output_path)
    return output_path.relative_to(paths.root).as_posix()


def build_market_baseline(
    *,
    event_id: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
    persist: bool = True,
) -> MarketBaselineDataset:
    effective_paths = paths or ProjectPaths.discover()
    rows = get_event_market_odds_as_of(
        event_id=event_id,
        decision_as_of=decision_as_of,
        paths=effective_paths,
    )
    records = _build_records(
        event_id=event_id,
        rows=rows,
        decision_as_of=decision_as_of,
    )
    relative_path = (
        _persist_records(
            paths=effective_paths,
            event_id=event_id,
            decision_as_of=decision_as_of,
            records=records,
        )
        if persist
        else None
    )
    return MarketBaselineDataset(records=records, relative_path=relative_path)
