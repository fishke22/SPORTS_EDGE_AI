from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sports_edge_ai.application.market_baseline import (
    MarketBaselineDataset,
    build_market_baseline,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    MarketBaselineRecord,
    NBAMoneylineFeatureRecord,
    NBAMoneylineTrainingSample,
)
from sports_edge_ai.infrastructure.db import connect_readonly


@dataclass(frozen=True, slots=True)
class LocalNBATrainingDataset:
    samples: tuple[NBAMoneylineTrainingSample, ...]
    candidate_event_count: int
    skipped_missing_odds: int
    skipped_non_decisive_result: int
    decisive_event_count: int = 0
    decision_odds_covered_count: int = 0
    closing_odds_covered_count: int = 0
    skipped_feature_error: int = 0


def _elo_expected(rating: float, opponent_rating: float) -> float:
    return float(1.0 / (1.0 + 10.0 ** ((opponent_rating - rating) / 400.0)))


def build_nba_feature_from_local_history(
    *,
    event_id: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
    initial_rating: float = 1500.0,
    k_factor: float = 20.0,
    default_rest_days: int = 7,
) -> NBAMoneylineFeatureRecord:
    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise ValueError("decision_as_of must be timezone-aware")
    if k_factor <= 0.0:
        raise ValueError("k_factor must be positive")
    if not 0 <= default_rest_days <= 14:
        raise ValueError("default_rest_days must be between 0 and 14")

    effective_paths = paths or ProjectPaths.discover()
    connection = connect_readonly(effective_paths)
    try:
        target = connection.execute(
            """
            SELECT home_team_id, away_team_id, scheduled_start, observed_at, sport
            FROM canonical_events
            WHERE event_id = ?
            """,
            [event_id],
        ).fetchone()
        if target is None:
            raise ValueError("canonical event not found")
        home_team_id = str(target[0])
        away_team_id = str(target[1])
        scheduled_start = target[2]
        event_observed_at = target[3]
        if str(target[4]) != "NBA":
            raise ValueError("target event must be NBA")
        if event_observed_at > decision_as_of:
            raise RuntimeError("target event was not observable at decision_as_of")
        if decision_as_of >= scheduled_start:
            raise ValueError("decision_as_of must precede scheduled_start")

        rating_rows = connection.execute(
            """
            WITH ranked AS (
                SELECT event.event_id, event.home_team_id, event.away_team_id,
                       event.scheduled_start, result.result_outcome,
                       result.observed_at,
                       row_number() OVER (
                           PARTITION BY result.event_id
                           ORDER BY result.observed_at DESC, result.event_result_id DESC
                       ) AS rn
                FROM event_results result
                JOIN canonical_events event ON event.event_id = result.event_id
                WHERE result.completed = TRUE
                  AND result.event_id IS NOT NULL
                  AND event.sport = 'NBA'
                  AND result.observed_at <= ?
                  AND event.scheduled_start < ?
            )
            SELECT event_id, home_team_id, away_team_id, scheduled_start,
                   result_outcome, observed_at
            FROM ranked
            WHERE rn = 1
            ORDER BY scheduled_start, event_id
            """,
            [decision_as_of, scheduled_start],
        ).fetchall()

    finally:
        connection.close()

    ratings: defaultdict[str, float] = defaultdict(lambda: initial_rating)
    last_game: dict[str, datetime] = {}
    max_input_observed_at = event_observed_at
    for row in rating_rows:
        history_home = str(row[1])
        history_away = str(row[2])
        outcome = str(row[4])
        observed_at = row[5]
        max_input_observed_at = max(max_input_observed_at, observed_at)
        if outcome == "HOME":
            actual_home = 1.0
        elif outcome == "AWAY":
            actual_home = 0.0
        elif outcome == "TIE":
            actual_home = 0.5
        else:
            continue
        expected_home = _elo_expected(ratings[history_home], ratings[history_away])
        adjustment = k_factor * (actual_home - expected_home)
        ratings[history_home] += adjustment
        ratings[history_away] -= adjustment
        last_game[history_home] = row[3]
        last_game[history_away] = row[3]

    def rest_days(team_id: str) -> int:
        previous = last_game.get(team_id)
        if previous is None:
            return default_rest_days
        elapsed = int((scheduled_start - previous).total_seconds() // 86400)
        return max(0, min(14, elapsed))

    return NBAMoneylineFeatureRecord(
        event_id=event_id,
        decision_as_of=decision_as_of,
        max_input_observed_at=max_input_observed_at,
        home_rating=ratings[home_team_id],
        away_rating=ratings[away_team_id],
        home_rest_days=rest_days(home_team_id),
        away_rest_days=rest_days(away_team_id),
        neutral_site=False,
    )


def _pair_groups(
    dataset: MarketBaselineDataset,
) -> dict[tuple[str, str, str], dict[str, MarketBaselineRecord]]:
    grouped: dict[tuple[str, str, str], dict[str, MarketBaselineRecord]] = {}
    for record in dataset.records:
        if record.market_type != "MONEYLINE" or record.period != "FULL_GAME":
            continue
        key = (record.bookmaker, record.source, record.market_group_id)
        grouped.setdefault(key, {})[record.selection] = record
    return {key: values for key, values in grouped.items() if set(values) == {"HOME", "AWAY"}}


def build_local_nba_training_samples(
    *,
    paths: ProjectPaths | None = None,
    decision_horizon_hours: int = 6,
) -> LocalNBATrainingDataset:
    if decision_horizon_hours <= 0:
        raise ValueError("decision_horizon_hours must be positive")
    effective_paths = paths or ProjectPaths.discover()
    connection = connect_readonly(effective_paths)
    try:
        rows = connection.execute(
            """
            WITH ranked AS (
                SELECT event.event_id, event.scheduled_start,
                       result.result_outcome, result.observed_at,
                       row_number() OVER (
                           PARTITION BY result.event_id
                           ORDER BY result.observed_at DESC, result.event_result_id DESC
                       ) AS rn
                FROM event_results result
                JOIN canonical_events event ON event.event_id = result.event_id
                WHERE result.completed = TRUE
                  AND result.event_id IS NOT NULL
                  AND event.sport = 'NBA'
            )
            SELECT event_id, scheduled_start, result_outcome, observed_at
            FROM ranked
            WHERE rn = 1
            ORDER BY scheduled_start, event_id
            """
        ).fetchall()
    finally:
        connection.close()

    samples: list[NBAMoneylineTrainingSample] = []
    skipped_missing_odds = 0
    skipped_non_decisive = 0
    decisive_event_count = 0
    decision_odds_covered_count = 0
    closing_odds_covered_count = 0
    skipped_feature_error = 0
    for event_id_raw, scheduled_start, outcome_raw, result_observed_at in rows:
        event_id = str(event_id_raw)
        outcome = str(outcome_raw)
        if outcome not in {"HOME", "AWAY"}:
            skipped_non_decisive += 1
            continue
        decisive_event_count += 1
        decision_as_of = scheduled_start - timedelta(hours=decision_horizon_hours)
        closing_as_of = scheduled_start - timedelta(microseconds=1)

        feature: NBAMoneylineFeatureRecord | None
        try:
            feature = build_nba_feature_from_local_history(
                event_id=event_id,
                decision_as_of=decision_as_of,
                paths=effective_paths,
            )
        except (ValueError, FileNotFoundError):
            feature = None
            skipped_feature_error += 1

        try:
            decision_dataset = build_market_baseline(
                event_id=event_id,
                decision_as_of=decision_as_of,
                paths=effective_paths,
                persist=False,
            )
            decision_groups = _pair_groups(decision_dataset)
        except (ValueError, FileNotFoundError):
            decision_groups = {}
        if decision_groups:
            decision_odds_covered_count += 1

        try:
            closing_dataset = build_market_baseline(
                event_id=event_id,
                decision_as_of=closing_as_of,
                paths=effective_paths,
                persist=False,
            )
            closing_groups = _pair_groups(closing_dataset)
        except (ValueError, FileNotFoundError):
            closing_groups = {}
        if closing_groups:
            closing_odds_covered_count += 1

        if feature is None:
            continue
        common = sorted(set(decision_groups).intersection(closing_groups))
        if not common:
            skipped_missing_odds += 1
            continue
        key = common[0]
        decision_pair = decision_groups[key]
        closing_pair = closing_groups[key]
        odds_observed_at = max(
            decision_pair["HOME"].max_input_observed_at,
            decision_pair["AWAY"].max_input_observed_at,
        )
        closing_observed_at = max(
            closing_pair["HOME"].max_input_observed_at,
            closing_pair["AWAY"].max_input_observed_at,
        )
        if closing_observed_at < decision_as_of:
            skipped_missing_odds += 1
            continue
        samples.append(
            NBAMoneylineTrainingSample(
                features=feature,
                home_win=outcome == "HOME",
                result_observed_at=result_observed_at,
                home_decimal_odds=decision_pair["HOME"].decimal_odds,
                away_decimal_odds=decision_pair["AWAY"].decimal_odds,
                odds_observed_at=odds_observed_at,
                closing_home_decimal_odds=closing_pair["HOME"].decimal_odds,
                closing_away_decimal_odds=closing_pair["AWAY"].decimal_odds,
                closing_observed_at=closing_observed_at,
                market_home_probability_fair=decision_pair["HOME"].market_probability_fair,
            )
        )

    return LocalNBATrainingDataset(
        samples=tuple(samples),
        candidate_event_count=len(rows),
        skipped_missing_odds=skipped_missing_odds,
        skipped_non_decisive_result=skipped_non_decisive,
        decisive_event_count=decisive_event_count,
        decision_odds_covered_count=decision_odds_covered_count,
        closing_odds_covered_count=closing_odds_covered_count,
        skipped_feature_error=skipped_feature_error,
    )
