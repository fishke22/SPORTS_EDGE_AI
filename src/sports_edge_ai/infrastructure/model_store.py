from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sports_edge_ai.application.calibration import PlattCalibrator
from sports_edge_ai.application.nba_baseline import NBALogisticBaselineModel
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import CalibrationRecord


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    relative_path: str
    sha256: str


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def persist_nba_model_artifact(
    model: NBALogisticBaselineModel,
    calibrator: PlattCalibrator,
    *,
    paths: ProjectPaths | None = None,
) -> ModelArtifact:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    if calibrator.record.model_id != model.model_id:
        raise ValueError("calibrator model_id does not match model")
    if calibrator.record.model_version != model.model_version:
        raise ValueError("calibrator model_version does not match model")
    if calibrator.record.feature_version != model.feature_version:
        raise ValueError("calibrator feature_version does not match model")
    payload: dict[str, object] = {
        "schema_version": "nba-model-artifact-v1",
        "model": {
            "model_id": model.model_id,
            "model_version": model.model_version,
            "feature_version": model.feature_version,
            "intercept": model.intercept,
            "rating_diff_weight": model.rating_diff_weight,
            "rest_diff_weight": model.rest_diff_weight,
            "home_court_weight": model.home_court_weight,
        },
        "calibration": calibrator.record.model_dump(mode="json"),
    }
    data = _canonical_bytes(payload)
    sha256 = hashlib.sha256(data).hexdigest()
    output_dir = effective_paths.models / model.model_id / model.model_version
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sha256}.json"

    if output_path.exists():
        if output_path.read_bytes() != data:
            raise RuntimeError("existing model artifact content does not match checksum path")
    else:
        output_path.write_bytes(data)

    return ModelArtifact(
        relative_path=output_path.relative_to(effective_paths.root).as_posix(),
        sha256=sha256,
    )


def load_nba_model_artifact(
    relative_path: str,
    *,
    paths: ProjectPaths | None = None,
) -> tuple[NBALogisticBaselineModel, PlattCalibrator]:
    effective_paths = paths or ProjectPaths.discover()
    path = (effective_paths.root / Path(relative_path)).resolve()
    root = effective_paths.root.resolve()
    models_root = effective_paths.models.resolve()
    try:
        path.relative_to(root)
        path.relative_to(models_root)
    except ValueError as exc:
        raise ValueError("model artifact path must be PROJECT_ROOT-relative under models/") from exc
    if not path.is_file():
        raise FileNotFoundError(path)

    data = path.read_bytes()
    expected_sha = path.stem
    actual_sha = hashlib.sha256(data).hexdigest()
    if expected_sha != actual_sha:
        raise RuntimeError("model artifact checksum mismatch")

    payload = json.loads(data.decode("utf-8"))
    if payload.get("schema_version") != "nba-model-artifact-v1":
        raise ValueError("unsupported model artifact schema version")
    model_payload = payload["model"]
    calibration_payload = payload["calibration"]
    model = NBALogisticBaselineModel(
        intercept=float(model_payload["intercept"]),
        rating_diff_weight=float(model_payload["rating_diff_weight"]),
        rest_diff_weight=float(model_payload["rest_diff_weight"]),
        home_court_weight=float(model_payload["home_court_weight"]),
        model_id=str(model_payload["model_id"]),
        model_version=str(model_payload["model_version"]),
        feature_version=str(model_payload["feature_version"]),
    )
    calibrator = PlattCalibrator(record=CalibrationRecord.model_validate(calibration_payload))
    if calibrator.record.model_id != model.model_id:
        raise RuntimeError("artifact calibration model_id mismatch")
    if calibrator.record.model_version != model.model_version:
        raise RuntimeError("artifact calibration model_version mismatch")
    if calibrator.record.feature_version != model.feature_version:
        raise RuntimeError("artifact calibration feature_version mismatch")
    return model, calibrator
