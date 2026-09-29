from __future__ import annotations

from dataclasses import dataclass

from sports_edge_ai.application.local_nba_research import (
    LocalNBATrainingDataset,
    build_local_nba_training_samples,
)
from sports_edge_ai.application.validation_gate import (
    evaluate_model_validation,
    research_validation_policy,
)
from sports_edge_ai.application.walk_forward_evaluator import evaluate_nba_walk_forward
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    EvidenceTier,
    ModelValidationDecision,
    WalkForwardEvaluationRecord,
)
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.rules_repository import get_payout_cost_rule


@dataclass(frozen=True, slots=True)
class LocalNBAResearchResult:
    status: str
    dataset: LocalNBATrainingDataset
    evaluation: WalkForwardEvaluationRecord | None
    validation: ModelValidationDecision | None


def evaluate_local_nba_dataset(
    dataset: LocalNBATrainingDataset,
    *,
    paths: ProjectPaths | None = None,
    min_train_size: int = 160,
    test_size: int = 20,
    calibration_size: int = 20,
    bootstrap_iterations: int = 1000,
) -> LocalNBAResearchResult:
    effective_paths = paths or ProjectPaths.discover()
    if len(dataset.samples) < min_train_size + test_size:
        return LocalNBAResearchResult(
            status="INSUFFICIENT_DATA",
            dataset=dataset,
            evaluation=None,
            validation=None,
        )

    rule = get_payout_cost_rule(
        rule_version="paper-decimal-zero-cost-v1",
        decision_as_of=dataset.samples[min_train_size].features.decision_as_of,
        paths=effective_paths,
    )
    evaluation = evaluate_nba_walk_forward(
        dataset.samples,
        payout_cost_rule=rule,
        min_train_size=min_train_size,
        test_size=test_size,
        step_size=test_size,
        calibration_size=calibration_size,
        bootstrap_iterations=bootstrap_iterations,
    )
    validation = evaluate_model_validation(
        evaluation,
        evidence_tier=EvidenceTier.HISTORICAL_POINT_IN_TIME,
        policy=research_validation_policy(),
    )
    return LocalNBAResearchResult(
        status="VALIDATED" if validation.is_model_validated else "RESEARCH_NOT_VALIDATED",
        dataset=dataset,
        evaluation=evaluation,
        validation=validation,
    )


def evaluate_local_nba_research(
    *,
    paths: ProjectPaths | None = None,
    decision_horizon_hours: int = 6,
    min_train_size: int = 160,
    test_size: int = 20,
    calibration_size: int = 20,
    bootstrap_iterations: int = 1000,
) -> LocalNBAResearchResult:
    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    dataset = build_local_nba_training_samples(
        paths=effective_paths,
        decision_horizon_hours=decision_horizon_hours,
    )
    return evaluate_local_nba_dataset(
        dataset,
        paths=effective_paths,
        min_train_size=min_train_size,
        test_size=test_size,
        calibration_size=calibration_size,
        bootstrap_iterations=bootstrap_iterations,
    )
