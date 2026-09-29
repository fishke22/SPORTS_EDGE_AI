from datetime import UTC, datetime

import pandera.errors
import polars as pl
import pytest

from sports_edge_ai.domain.frame_contracts import ODDS_SNAPSHOT_FRAME_SCHEMA


def _frame(decimal_odds: float = 1.91) -> pl.DataFrame:
    observed_at = datetime(2026, 10, 1, 8, tzinfo=UTC)
    return pl.DataFrame(
        {
            "event_id": ["SYNTH_NBA_001"],
            "market_id": ["SYNTH_NBA_001_ML"],
            "bookmaker": ["synthetic"],
            "source": ["synthetic"],
            "decimal_odds": [decimal_odds],
            "observed_at": [observed_at],
            "ingested_at": [observed_at],
            "is_live": [False],
            "is_closing": [False],
            "raw_source_ref": ["fixtures/synthetic/nba_moneyline_snapshot.json"],
            "payload_hash": ["a" * 64],
        }
    )


def test_pandera_polars_contract_accepts_canonical_odds() -> None:
    validated = ODDS_SNAPSHOT_FRAME_SCHEMA.validate(_frame())
    assert validated.height == 1


def test_pandera_polars_contract_rejects_invalid_odds() -> None:
    with pytest.raises(pandera.errors.SchemaError):
        ODDS_SNAPSHOT_FRAME_SCHEMA.validate(_frame(1.0))
