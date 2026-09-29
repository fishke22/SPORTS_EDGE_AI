from __future__ import annotations

import json

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import BacktestRecord, ModelRegistryRecord
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def get_model_registry_record(
    *,
    model_id: str,
    model_version: str,
    paths: ProjectPaths | None = None,
) -> ModelRegistryRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT model_id, model_version, sport, market_type,
                   training_window_start, training_window_end,
                   validation_window_start, validation_window_end,
                   feature_version, calibration_version, artifact_path,
                   artifact_sha256, created_at, status, metrics_json
            FROM model_registry
            WHERE model_id = ? AND model_version = ?
            """,
            [model_id, model_version],
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None
    metrics = json.loads(row[14]) if isinstance(row[14], str) else row[14]
    return ModelRegistryRecord(
        model_id=row[0],
        model_version=row[1],
        sport=row[2],
        market_type=row[3],
        training_window_start=row[4],
        training_window_end=row[5],
        validation_window_start=row[6],
        validation_window_end=row[7],
        feature_version=row[8],
        calibration_version=row[9],
        artifact_path=row[10],
        artifact_sha256=row[11],
        created_at=row[12],
        status=row[13],
        metrics_json=metrics,
    )


def get_backtest_record(
    *,
    backtest_id: str,
    paths: ProjectPaths | None = None,
) -> BacktestRecord | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT backtest_id, model_id, model_version, sport, market_type,
                   test_window_start, test_window_end, sample_count, brier,
                   log_loss, ece, roi, yield_rate, clv, max_drawdown,
                   bootstrap_ci_low, bootstrap_ci_high, created_at
            FROM backtest_runs
            WHERE backtest_id = ?
            """,
            [backtest_id],
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None
    return BacktestRecord(
        backtest_id=row[0],
        model_id=row[1],
        model_version=row[2],
        sport=row[3],
        market_type=row[4],
        test_window_start=row[5],
        test_window_end=row[6],
        sample_count=row[7],
        brier=row[8],
        log_loss=row[9],
        ece=row[10],
        roi=row[11],
        yield_rate=row[12],
        clv=row[13],
        max_drawdown=row[14],
        bootstrap_ci_low=row[15],
        bootstrap_ci_high=row[16],
        created_at=row[17],
    )


def persist_model_registry_record(
    record: ModelRegistryRecord,
    *,
    paths: ProjectPaths | None = None,
) -> None:
    connection = connect(paths)
    try:
        existing = connection.execute(
            """
            SELECT model_id, model_version, sport, market_type,
                   training_window_start, training_window_end,
                   validation_window_start, validation_window_end,
                   feature_version, calibration_version, artifact_path,
                   artifact_sha256, created_at, status, metrics_json
            FROM model_registry
            WHERE model_id = ? AND model_version = ?
            """,
            [record.model_id, record.model_version],
        ).fetchone()
        if existing is not None:
            existing_metrics = (
                json.loads(existing[14]) if isinstance(existing[14], str) else existing[14]
            )
            existing_record = ModelRegistryRecord(
                model_id=existing[0],
                model_version=existing[1],
                sport=existing[2],
                market_type=existing[3],
                training_window_start=existing[4],
                training_window_end=existing[5],
                validation_window_start=existing[6],
                validation_window_end=existing[7],
                feature_version=existing[8],
                calibration_version=existing[9],
                artifact_path=existing[10],
                artifact_sha256=existing[11],
                created_at=existing[12],
                status=existing[13],
                metrics_json=existing_metrics,
            )
            if existing_record != record:
                raise RuntimeError("model registry version already exists with different content")
            return

        connection.execute(
            """
            INSERT INTO model_registry VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.model_id,
                record.model_version,
                record.sport,
                record.market_type,
                record.training_window_start,
                record.training_window_end,
                record.validation_window_start,
                record.validation_window_end,
                record.feature_version,
                record.calibration_version,
                record.artifact_path,
                record.artifact_sha256,
                record.created_at,
                record.status,
                json.dumps(record.metrics_json, sort_keys=True),
            ],
        )
    finally:
        connection.close()


def persist_backtest_record(
    record: BacktestRecord,
    *,
    paths: ProjectPaths | None = None,
) -> None:
    connection = connect(paths)
    try:
        existing = connection.execute(
            """
            SELECT backtest_id, model_id, model_version, sport, market_type,
                   test_window_start, test_window_end, sample_count, brier,
                   log_loss, ece, roi, yield_rate, clv, max_drawdown,
                   bootstrap_ci_low, bootstrap_ci_high, created_at
            FROM backtest_runs
            WHERE backtest_id = ?
            """,
            [record.backtest_id],
        ).fetchone()
        if existing is not None:
            existing_record = BacktestRecord(
                backtest_id=existing[0],
                model_id=existing[1],
                model_version=existing[2],
                sport=existing[3],
                market_type=existing[4],
                test_window_start=existing[5],
                test_window_end=existing[6],
                sample_count=existing[7],
                brier=existing[8],
                log_loss=existing[9],
                ece=existing[10],
                roi=existing[11],
                yield_rate=existing[12],
                clv=existing[13],
                max_drawdown=existing[14],
                bootstrap_ci_low=existing[15],
                bootstrap_ci_high=existing[16],
                created_at=existing[17],
            )
            if existing_record != record:
                raise RuntimeError("backtest id already exists with different content")
            return

        connection.execute(
            """
            INSERT INTO backtest_runs VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.backtest_id,
                record.model_id,
                record.model_version,
                record.sport,
                record.market_type,
                record.test_window_start,
                record.test_window_end,
                record.sample_count,
                record.brier,
                record.log_loss,
                record.ece,
                record.roi,
                record.yield_rate,
                record.clv,
                record.max_drawdown,
                record.bootstrap_ci_low,
                record.bootstrap_ci_high,
                record.created_at,
            ],
        )
    finally:
        connection.close()
