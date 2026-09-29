from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sports_edge_ai.domain.schemas import CanonicalEvent, OddsSnapshot


def _event(**overrides):
    values = {
        "event_id": "event-1",
        "sport": "NBA",
        "league": "NBA",
        "home_team_id": "team-home",
        "away_team_id": "team-away",
        "scheduled_start": datetime(2026, 10, 1, 12, tzinfo=UTC),
        "observed_at": datetime(2026, 9, 30, 8, tzinfo=UTC),
        "ingested_at": datetime(2026, 9, 30, 8, 0, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return CanonicalEvent(**values)


def test_event_requires_timezone_aware_timestamps() -> None:
    assert _event().sport == "NBA"

    with pytest.raises(ValidationError):
        _event(scheduled_start=datetime(2026, 10, 1, 12))


def test_odds_source_reference_must_be_project_relative() -> None:
    absolute_ref = "Z" + ":" + "/portable/data/raw.json"
    with pytest.raises(ValidationError):
        OddsSnapshot(
            odds_snapshot_id="odds-1",
            event_id="event-1",
            market_id="market-1",
            bookmaker="synthetic",
            source="synthetic",
            decimal_odds=1.91,
            observed_at=datetime(2026, 9, 30, 8, tzinfo=UTC),
            ingested_at=datetime(2026, 9, 30, 8, 0, 1, tzinfo=UTC),
            raw_source_ref=absolute_ref,
            payload_hash="a" * 64,
        )
