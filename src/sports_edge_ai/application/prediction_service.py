from __future__ import annotations

import hashlib
from pathlib import Path

from sports_edge_ai.application.market_analysis import analyze_market
from sports_edge_ai.application.market_baseline import build_market_baseline
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    NBAMoneylineFeatureRecord,
    PredictionRecord,
)
from sports_edge_ai.infrastructure.model_repository import get_model_registry_record
from sports_edge_ai.infrastructure.model_store import load_nba_model_artifact
from sports_edge_ai.infrastructure.prediction_repository import persist_prediction_record


def generate_nba_prediction_records(
    *,
    feature: NBAMoneylineFeatureRecord,
    model_id: str,
    model_version: str,
    payout_cost_rule_version: str = "paper-decimal-zero-cost-v1",
    uncertainty: float = 0.10,
    data_quality: DataQualityStatus = DataQualityStatus.GREEN,
    paths: ProjectPaths | None = None,
) -> tuple[PredictionRecord, ...]:
    effective_paths = paths or ProjectPaths.discover()
    registry = get_model_registry_record(
        model_id=model_id,
        model_version=model_version,
        paths=effective_paths,
    )
    if registry is None:
        raise ValueError("model registry record not found")
    if registry.sport != "NBA" or registry.market_type != "MONEYLINE":
        raise ValueError("model registry record is not an NBA moneyline model")
    if Path(registry.artifact_path).stem != registry.artifact_sha256:
        raise RuntimeError("model registry artifact checksum does not match artifact path")

    model, calibrator = load_nba_model_artifact(
        registry.artifact_path,
        paths=effective_paths,
    )
    if model.model_id != registry.model_id or model.model_version != registry.model_version:
        raise RuntimeError("model artifact identity does not match registry")
    if model.feature_version != feature.feature_version:
        raise ValueError("feature version does not match registered model artifact")

    raw_home_probability = model.predict_home_probability(feature)
    calibrated_home_probability = calibrator.calibrate(
        raw_home_probability,
        decision_as_of=feature.decision_as_of,
    )
    calibrated_probabilities = {
        "HOME": calibrated_home_probability,
        "AWAY": 1.0 - calibrated_home_probability,
    }
    raw_probabilities = {
        "HOME": raw_home_probability,
        "AWAY": 1.0 - raw_home_probability,
    }
    is_validated = registry.status == "VALIDATED"
    analysis = analyze_market(
        event_id=feature.event_id,
        decision_as_of=feature.decision_as_of,
        model_probabilities=calibrated_probabilities,
        payout_cost_rule_version=payout_cost_rule_version,
        uncertainty=uncertainty,
        data_quality=data_quality,
        model_validated=is_validated,
        paths=effective_paths,
    )
    baseline = build_market_baseline(
        event_id=feature.event_id,
        decision_as_of=feature.decision_as_of,
        paths=effective_paths,
        persist=False,
    )
    baseline_by_key = {(row.market_id, row.bookmaker, row.source): row for row in baseline.records}

    predictions: list[PredictionRecord] = []
    for record in analysis:
        base = baseline_by_key.get((record.market_id, record.bookmaker, record.source))
        if base is None:
            raise RuntimeError("market analysis record has no matching baseline provenance")
        if base.odds_snapshot_id is None:
            raise RuntimeError("baseline record is missing odds_snapshot_id")
        material = (
            f"{registry.model_id}|{registry.model_version}|{feature.event_id}|"
            f"{record.market_id}|{record.bookmaker}|{record.source}|"
            f"{feature.decision_as_of.isoformat()}|{base.odds_snapshot_id}"
        ).encode()
        prediction = PredictionRecord(
            prediction_id=hashlib.sha256(material).hexdigest()[:32],
            event_id=feature.event_id,
            market_id=record.market_id,
            model_id=registry.model_id,
            model_version=registry.model_version,
            feature_version=feature.feature_version,
            calibration_version=registry.calibration_version,
            model_probability_raw=raw_probabilities[record.selection],
            model_probability_calibrated=record.model_probability,
            market_probability_raw=base.market_probability_raw,
            market_probability_fair=record.market_probability_fair,
            fair_odds=record.model_fair_odds,
            edge=record.edge,
            gross_ev=record.gross_ev,
            net_ev=record.net_ev,
            uncertainty=record.uncertainty,
            data_quality=record.data_quality,
            recommendation=record.recommendation,
            generated_at=feature.decision_as_of,
            as_of=feature.decision_as_of,
            bookmaker=record.bookmaker,
            source=record.source,
            odds_snapshot_id=base.odds_snapshot_id,
        )
        persist_prediction_record(prediction, paths=effective_paths)
        predictions.append(prediction)
    return tuple(predictions)
