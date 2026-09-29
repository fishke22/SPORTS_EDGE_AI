from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sports_edge_ai.application.calibration import PlattCalibrator
from sports_edge_ai.application.nba_baseline import NBALogisticBaselineModel
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    BacktestRecord,
    ModelRegistryRecord,
    ModelValidationDecision,
    NBAMoneylineTrainingSample,
    WalkForwardEvaluationRecord,
)
from sports_edge_ai.infrastructure.model_repository import (
    persist_backtest_record,
    persist_model_registry_record,
)
from sports_edge_ai.infrastructure.model_store import (
    ModelArtifact,
    persist_nba_model_artifact,
)


@dataclass(frozen=True, slots=True)
class ModelLifecycleResult:
    artifact: ModelArtifact
    registry_record: ModelRegistryRecord
    backtest_record: BacktestRecord
    report_relative_path: str


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def persist_nba_research_lifecycle(
    *,
    model: NBALogisticBaselineModel,
    calibrator: PlattCalibrator,
    training_samples: Sequence[NBAMoneylineTrainingSample],
    evaluation: WalkForwardEvaluationRecord,
    validation_decision: ModelValidationDecision,
    created_at: datetime,
    paths: ProjectPaths | None = None,
) -> ModelLifecycleResult:
    if not training_samples:
        raise ValueError("training_samples must not be empty")
    if calibrator.record.model_id != model.model_id:
        raise ValueError("calibrator model_id does not match model")
    if calibrator.record.model_version != model.model_version:
        raise ValueError("calibrator model_version does not match model")
    if calibrator.record.feature_version != model.feature_version:
        raise ValueError("calibrator feature_version does not match model")
    if evaluation.model_id != model.model_id or evaluation.model_version != model.model_version:
        raise ValueError("evaluation model identity does not match model")
    if evaluation.feature_version != model.feature_version:
        raise ValueError("evaluation feature_version does not match model")
    if evaluation.calibration_version != calibrator.record.calibration_version:
        raise ValueError("evaluation calibration_version does not match calibrator")
    if calibrator.record.fitted_at > evaluation.test_window_start:
        raise ValueError("calibration must be fitted before validation window starts")

    effective_paths = paths or ProjectPaths.discover()
    artifact = persist_nba_model_artifact(model, calibrator, paths=effective_paths)
    report_payload: dict[str, object] = {
        "schema_version": "backtest-report-v1",
        "artifact": {
            "relative_path": artifact.relative_path,
            "sha256": artifact.sha256,
        },
        "calibration": calibrator.record.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json"),
        "validation_gate": validation_decision.model_dump(mode="json"),
    }
    report_json = _canonical_json(report_payload)
    backtest_id = hashlib.sha256(report_json.encode("utf-8")).hexdigest()[:32]
    report_dir = effective_paths.reports / "backtests"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{backtest_id}.json"
    if report_path.exists():
        if report_path.read_text(encoding="utf-8") != report_json:
            raise RuntimeError("existing backtest report differs from deterministic id")
    else:
        report_path.write_text(report_json, encoding="utf-8")
    report_relative_path = report_path.relative_to(effective_paths.root).as_posix()

    backtest_record = BacktestRecord(
        backtest_id=backtest_id,
        model_id=model.model_id,
        model_version=model.model_version,
        sport="NBA",
        market_type="MONEYLINE",
        test_window_start=evaluation.test_window_start,
        test_window_end=evaluation.test_window_end,
        sample_count=evaluation.sample_count,
        brier=evaluation.brier,
        log_loss=evaluation.log_loss,
        ece=evaluation.ece,
        roi=evaluation.roi,
        yield_rate=evaluation.yield_rate,
        clv=evaluation.clv,
        max_drawdown=evaluation.max_drawdown,
        bootstrap_ci_low=evaluation.bootstrap_ci_low,
        bootstrap_ci_high=evaluation.bootstrap_ci_high,
        created_at=created_at,
    )
    training_window_start = min(sample.features.decision_as_of for sample in training_samples)
    training_window_end = max(sample.features.decision_as_of for sample in training_samples)
    registry_record = ModelRegistryRecord(
        model_id=model.model_id,
        model_version=model.model_version,
        sport="NBA",
        market_type="MONEYLINE",
        training_window_start=training_window_start,
        training_window_end=training_window_end,
        validation_window_start=evaluation.test_window_start,
        validation_window_end=evaluation.test_window_end,
        feature_version=model.feature_version,
        calibration_version=calibrator.record.calibration_version,
        artifact_path=artifact.relative_path,
        artifact_sha256=artifact.sha256,
        created_at=created_at,
        status=(
            "VALIDATED" if validation_decision.is_model_validated else "RESEARCH_NOT_VALIDATED"
        ),
        metrics_json={
            "backtest_id": backtest_id,
            "backtest_report": report_relative_path,
            "calibration": calibrator.record.model_dump(mode="json"),
            "evaluation": evaluation.model_dump(mode="json"),
            "validation_gate": validation_decision.model_dump(mode="json"),
        },
    )

    persist_backtest_record(backtest_record, paths=effective_paths)
    persist_model_registry_record(registry_record, paths=effective_paths)
    return ModelLifecycleResult(
        artifact=artifact,
        registry_record=registry_record,
        backtest_record=backtest_record,
        report_relative_path=report_relative_path,
    )
