from __future__ import annotations

import pandera.polars as pa
import polars as pl

ODDS_SNAPSHOT_FRAME_SCHEMA = pa.DataFrameSchema(
    {
        "event_id": pa.Column(pl.String, nullable=False),
        "market_id": pa.Column(pl.String, nullable=False),
        "bookmaker": pa.Column(pl.String, nullable=False),
        "source": pa.Column(pl.String, nullable=False),
        "decimal_odds": pa.Column(
            pl.Float64,
            checks=pa.Check.gt(1.0),
            nullable=False,
        ),
        "observed_at": pa.Column(
            pl.Datetime(time_zone="UTC"),
            nullable=False,
        ),
        "ingested_at": pa.Column(
            pl.Datetime(time_zone="UTC"),
            nullable=False,
        ),
        "is_live": pa.Column(pl.Boolean, nullable=False),
        "is_closing": pa.Column(pl.Boolean, nullable=False),
        "raw_source_ref": pa.Column(pl.String, nullable=False),
        "payload_hash": pa.Column(pl.String, nullable=False),
    },
    strict=True,
    coerce=False,
    name="odds_snapshot_v1",
)
