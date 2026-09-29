from __future__ import annotations

from typing import Any

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import DataQualityStatus, PredictionRecord, Recommendation
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def _from_row(row: tuple[Any, ...]) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=str(row[0]),
        schema_version=str(row[1]),
        event_id=str(row[2]),
        market_id=str(row[3]),
        model_id=str(row[4]),
        model_version=str(row[5]),
        feature_version=str(row[6]),
        calibration_version=str(row[7]),
        model_probability_raw=float(row[8]),
        model_probability_calibrated=float(row[9]),
        market_probability_raw=None if row[10] is None else float(row[10]),
        market_probability_fair=None if row[11] is None else float(row[11]),
        fair_odds=float(row[12]),
        edge=float(row[13]),
        gross_ev=float(row[14]),
        net_ev=float(row[15]),
        uncertainty=float(row[16]),
        data_quality=DataQualityStatus(str(row[17])),
        recommendation=Recommendation(str(row[18])),
        generated_at=row[19],
        as_of=row[20],
        bookmaker=row[21] if len(row) > 21 else None,
        source=row[22] if len(row) > 22 else None,
        odds_snapshot_id=row[23] if len(row) > 23 else None,
    )


def get_prediction_record(
    *,
    prediction_id: str,
    paths: ProjectPaths | None = None,
) -> PredictionRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            "SELECT * FROM predictions WHERE prediction_id = ?",
            [prediction_id],
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else _from_row(row)


def persist_prediction_record(
    record: PredictionRecord,
    *,
    paths: ProjectPaths | None = None,
) -> None:
    connection = connect(paths)
    try:
        existing = connection.execute(
            "SELECT * FROM predictions WHERE prediction_id = ?",
            [record.prediction_id],
        ).fetchone()
        if existing is not None:
            if _from_row(existing) != record:
                raise RuntimeError("prediction id already exists with different content")
            return
        connection.execute(
            """
            INSERT INTO predictions (
                prediction_id, schema_version, event_id, market_id, model_id,
                model_version, feature_version, calibration_version,
                model_probability_raw, model_probability_calibrated,
                market_probability_raw, market_probability_fair, fair_odds,
                edge, gross_ev, net_ev, uncertainty, data_quality,
                recommendation, generated_at, as_of, bookmaker, source,
                odds_snapshot_id
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.prediction_id,
                record.schema_version,
                record.event_id,
                record.market_id,
                record.model_id,
                record.model_version,
                record.feature_version,
                record.calibration_version,
                record.model_probability_raw,
                record.model_probability_calibrated,
                record.market_probability_raw,
                record.market_probability_fair,
                record.fair_odds,
                record.edge,
                record.gross_ev,
                record.net_ev,
                record.uncertainty,
                record.data_quality,
                record.recommendation,
                record.generated_at,
                record.as_of,
                record.bookmaker,
                record.source,
                record.odds_snapshot_id,
            ],
        )
    finally:
        connection.close()
