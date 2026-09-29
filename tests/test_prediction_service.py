from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from sports_edge_ai.application.calibration import PlattCalibrator
from sports_edge_ai.application.nba_baseline import NBALogisticBaselineModel
from sports_edge_ai.application.prediction_service import generate_nba_prediction_records
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    CalibrationRecord,
    DataQualityStatus,
    ModelRegistryRecord,
    NBAMoneylineFeatureRecord,
    Recommendation,
)
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.model_repository import persist_model_registry_record
from sports_edge_ai.infrastructure.model_store import persist_nba_model_artifact
from sports_edge_ai.infrastructure.prediction_repository import get_prediction_record

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_prediction_service_persists_as_of_odds_provenance(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    ingest_synthetic_snapshot(
        PROJECT_ROOT / "fixtures" / "synthetic" / "nba_moneyline_snapshot.json",
        paths=paths,
    )
    migrate(paths)

    model = NBALogisticBaselineModel(
        intercept=0.0,
        rating_diff_weight=0.60,
        rest_diff_weight=0.0,
        home_court_weight=0.0,
    )
    calibrator = PlattCalibrator(
        record=CalibrationRecord(
            calibration_version="platt-v1",
            model_id=model.model_id,
            model_version=model.model_version,
            feature_version=model.feature_version,
            training_window_end=datetime(2026, 6, 1, tzinfo=UTC),
            calibration_window_start=datetime(2026, 6, 2, tzinfo=UTC),
            calibration_window_end=datetime(2026, 6, 30, tzinfo=UTC),
            fitted_at=datetime(2026, 7, 1, tzinfo=UTC),
            sample_count=20,
            intercept=0.0,
            slope=1.0,
        )
    )
    artifact = persist_nba_model_artifact(model, calibrator, paths=paths)
    persist_model_registry_record(
        ModelRegistryRecord(
            model_id=model.model_id,
            model_version=model.model_version,
            sport="NBA",
            market_type="MONEYLINE",
            training_window_start=datetime(2026, 1, 1, tzinfo=UTC),
            training_window_end=datetime(2026, 6, 1, tzinfo=UTC),
            validation_window_start=datetime(2026, 7, 2, tzinfo=UTC),
            validation_window_end=datetime(2026, 8, 1, tzinfo=UTC),
            feature_version=model.feature_version,
            calibration_version=calibrator.record.calibration_version,
            artifact_path=artifact.relative_path,
            artifact_sha256=artifact.sha256,
            created_at=datetime(2026, 8, 2, tzinfo=UTC),
            status="RESEARCH_NOT_VALIDATED",
            metrics_json={"source": "test"},
        ),
        paths=paths,
    )
    feature = NBAMoneylineFeatureRecord(
        event_id="SYNTH_NBA_001",
        decision_as_of=datetime(2026, 10, 1, 8, 30, tzinfo=UTC),
        max_input_observed_at=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
        home_rating=1560.0,
        away_rating=1440.0,
        home_rest_days=3,
        away_rest_days=2,
    )

    records = generate_nba_prediction_records(
        feature=feature,
        model_id=model.model_id,
        model_version=model.model_version,
        data_quality=DataQualityStatus.GREEN,
        paths=paths,
    )

    assert len(records) == 2
    assert {record.recommendation for record in records} <= {
        Recommendation.NO_BET,
        Recommendation.NO_VALIDATED_EDGE,
    }
    assert all(record.odds_snapshot_id for record in records)
    assert all(record.bookmaker == "SYNTHETIC_BOOK" for record in records)
    assert all(record.source == "synthetic_nba" for record in records)
    stored = get_prediction_record(prediction_id=records[0].prediction_id, paths=paths)
    assert stored == records[0]
