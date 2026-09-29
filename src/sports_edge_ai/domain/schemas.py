from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Recommendation(StrEnum):
    NO_BET = "NO_BET"
    NO_VALIDATED_EDGE = "NO_VALIDATED_EDGE"
    WATCH = "WATCH"
    EDGE = "EDGE"
    DATA_CONFLICT = "DATA_CONFLICT"


class DataQualityStatus(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class EvidenceTier(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    HISTORICAL_POINT_IN_TIME = "HISTORICAL_POINT_IN_TIME"
    LIVE_PAPER = "LIVE_PAPER"


class ResearchReadinessStatus(StrEnum):
    NOT_READY = "NOT_READY"
    EVALUATION_READY = "EVALUATION_READY"
    VALIDATION_SAMPLE_READY = "VALIDATION_SAMPLE_READY"


class ResearchCycleStatus(StrEnum):
    NOT_READY = "NOT_READY"
    SKIPPED_UNCHANGED = "SKIPPED_UNCHANGED"
    EVALUATED_NOT_VALIDATED = "EVALUATED_NOT_VALIDATED"
    EVALUATED_GATE_PASSED = "EVALUATED_GATE_PASSED"
    FAILED = "FAILED"


class OperationalSeverity(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="after")
    @classmethod
    def require_timezone_aware_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime fields must be timezone-aware")
        return value


class CanonicalEvent(ContractModel):
    event_id: str
    schema_version: str = "event-v1"
    sport: str
    league: str
    season: str | None = None
    home_team_id: str
    away_team_id: str
    scheduled_start: datetime
    venue_id: str | None = None
    status: str = "SCHEDULED"
    source_event_ids: dict[str, str] = Field(default_factory=dict)
    effective_at: datetime | None = None
    observed_at: datetime
    ingested_at: datetime


class CanonicalMarket(ContractModel):
    market_id: str
    schema_version: str = "market-v1"
    event_id: str
    market_type: str
    period: str = "FULL_GAME"
    selection: str
    line: float | None = None
    market_rules_version: str = "market-rules-v1"


class OddsSnapshot(ContractModel):
    odds_snapshot_id: str
    schema_version: str = "odds-v1"
    event_id: str
    market_id: str
    bookmaker: str
    source: str
    decimal_odds: float = Field(gt=1.0)
    observed_at: datetime
    provider_timestamp: datetime | None = None
    ingested_at: datetime
    is_live: bool = False
    is_closing: bool = False
    raw_source_ref: str = Field(min_length=1)
    payload_hash: str = Field(min_length=64, max_length=64)

    @field_validator("raw_source_ref")
    @classmethod
    def require_relative_source_ref(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if not path.parts or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
            raise ValueError("raw_source_ref must be a PROJECT_ROOT-relative path")
        return normalized


class PredictionRecord(ContractModel):
    prediction_id: str
    schema_version: str = "prediction-v1"
    event_id: str
    market_id: str
    model_id: str
    model_version: str
    feature_version: str
    calibration_version: str
    model_probability_raw: float = Field(ge=0.0, le=1.0)
    model_probability_calibrated: float = Field(ge=0.0, le=1.0)
    market_probability_raw: float | None = Field(default=None, ge=0.0)
    market_probability_fair: float | None = Field(default=None, ge=0.0, le=1.0)
    fair_odds: float = Field(gt=1.0)
    edge: float
    gross_ev: float
    net_ev: float
    uncertainty: float = Field(ge=0.0, le=1.0)
    data_quality: DataQualityStatus
    recommendation: Recommendation
    generated_at: datetime
    as_of: datetime
    bookmaker: str | None = None
    source: str | None = None
    odds_snapshot_id: str | None = None


class ModelRegistryRecord(ContractModel):
    model_id: str
    model_version: str
    sport: str
    market_type: str
    training_window_start: datetime
    training_window_end: datetime
    validation_window_start: datetime
    validation_window_end: datetime
    feature_version: str
    calibration_version: str
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime
    status: str
    metrics_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_path")
    @classmethod
    def require_relative_artifact_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if not path.parts or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
            raise ValueError("artifact_path must be a PROJECT_ROOT-relative path")
        return normalized


class BacktestRecord(ContractModel):
    backtest_id: str
    model_id: str
    model_version: str
    sport: str
    market_type: str
    test_window_start: datetime
    test_window_end: datetime
    sample_count: int = Field(ge=0)
    brier: float | None = None
    log_loss: float | None = None
    ece: float | None = None
    roi: float | None = None
    yield_rate: float | None = None
    clv: float | None = None
    max_drawdown: float | None = None
    bootstrap_ci_low: float | None = None
    bootstrap_ci_high: float | None = None
    created_at: datetime


class PaperTradeRecord(ContractModel):
    paper_trade_id: str
    prediction_id: str
    event_id: str
    market_id: str
    decision_at: datetime
    odds_snapshot_id: str
    odds_decimal: float = Field(gt=1.0)
    stake: float = Field(gt=0.0)
    status: str
    model_version: str
    settlement_rule_version: str


class SettlementRecord(ContractModel):
    settlement_id: str
    paper_trade_id: str | None = None
    event_id: str
    market_id: str
    settlement_status: str
    market_result: str | None = None
    void_reason: str | None = None
    payout_rule_version: str
    tax_rule_version: str
    gross_payout: float = Field(ge=0.0)
    net_payout: float = Field(ge=0.0)
    pnl: float
    settled_at: datetime


class RiskRecord(ContractModel):
    risk_assessment_id: str
    prediction_id: str
    recommendation: Recommendation
    data_quality: DataQualityStatus
    uncertainty: float = Field(ge=0.0, le=1.0)
    risk_blockers: tuple[str, ...] = ()
    evaluated_at: datetime


class DataQualityRecord(ContractModel):
    data_quality_id: str
    provider: str
    observed_at: datetime
    status: DataQualityStatus
    freshness_seconds: int = Field(ge=0)
    missing_rate: float = Field(ge=0.0, le=1.0)
    duplicate_rate: float = Field(ge=0.0, le=1.0)
    mapping_rate: float = Field(ge=0.0, le=1.0)
    schema_version: str
    message: str | None = None


class SourceLicenseRecord(ContractModel):
    license_id: str
    provider: str
    data_type: str
    license_name: str | None = None
    commercial_allowed: bool | None = None
    redistribution_allowed: bool | None = None
    attribution_required: bool = False
    automated_access_allowed: bool | None = None
    credential_required: bool = False
    reviewed_at: datetime
    source_terms_ref: str | None = None
    notes: str | None = None


class ProviderRecord(ContractModel):
    provider_id: str
    provider_name: str
    provider_type: str
    official_url: str | None = None
    api_version: str | None = None
    auth_type: str | None = None
    license_id: str | None = None
    enabled: bool = True
    production_allowed: bool = False
    last_reviewed_at: datetime | None = None


class CanonicalEntityRecord(ContractModel):
    entity_id: str
    entity_kind: str
    sport: str | None = None
    canonical_name: str
    active: bool = True
    created_at: datetime


class ProviderEntityMappingRecord(ContractModel):
    provider_id: str
    entity_kind: str
    provider_entity_id: str
    canonical_entity_id: str
    observed_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    resolution_method: str


class ProviderUsageSnapshot(ContractModel):
    provider_id: str
    observed_at: datetime
    requests_remaining: int | None = Field(default=None, ge=0)
    requests_used: int | None = Field(default=None, ge=0)
    requests_last: int | None = Field(default=None, ge=0)
    local_monthly_budget: int = Field(gt=0)
    endpoint_kind: str


class ForwardCollectionRunRecord(ContractModel):
    collection_run_id: str
    provider_id: str
    trigger_kind: str
    started_at: datetime
    finished_at: datetime
    status: str
    current_due: bool
    scores_due: bool
    current_attempted: bool
    scores_attempted: bool
    events_count: int = Field(ge=0)
    odds_count: int = Field(ge=0)
    results_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    data_quality_status: DataQualityStatus | None = None
    mapping_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    requests_used_before: int | None = Field(default=None, ge=0)
    requests_used_after: int | None = Field(default=None, ge=0)
    credits_spent: int | None = Field(default=None, ge=0)
    requests_remaining_after: int | None = Field(default=None, ge=0)
    error_summary: str | None = None


class ForwardCollectionStatusRecord(ContractModel):
    provider_id: str
    checked_at: datetime
    current_min_interval_minutes: int = Field(gt=0)
    scores_min_interval_minutes: int = Field(gt=0)
    current_due: bool
    scores_due: bool
    last_current_at: datetime | None = None
    last_scores_at: datetime | None = None
    latest_run: ForwardCollectionRunRecord | None = None
    requests_used: int | None = Field(default=None, ge=0)
    requests_remaining: int | None = Field(default=None, ge=0)
    live_event_count: int = Field(ge=0)
    odds_snapshot_count: int = Field(ge=0)
    completed_result_count: int = Field(ge=0)
    past_event_without_result_count: int = Field(ge=0)
    next_event_start: datetime | None = None


class ProviderEntityProposalRecord(ContractModel):
    provider_id: str
    entity_kind: str
    provider_entity_id: str
    provider_display_name: str
    provider_object_id: str | None = None
    proposed_canonical_entity_id: str | None = None
    proposal_method: str
    status: str
    observed_at: datetime
    reviewed_at: datetime | None = None
    review_note: str | None = None


class ProviderMappingReviewSummary(ContractModel):
    provider_id: str
    entity_kind: str
    proposal_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    approved_mapping_count: int = Field(ge=0)
    review_completion_rate: float = Field(ge=0.0, le=1.0)


class EventResultRecord(ContractModel):
    event_result_id: str
    event_id: str | None = None
    provider_id: str
    provider_event_id: str
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)
    result_outcome: str | None = None
    completed: bool
    observed_at: datetime
    provider_timestamp: datetime | None = None
    raw_source_ref: str
    payload_hash: str = Field(min_length=64, max_length=64)

    @field_validator("raw_source_ref")
    @classmethod
    def require_relative_result_source_ref(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if not path.parts or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
            raise ValueError("raw_source_ref must be a PROJECT_ROOT-relative path")
        return normalized


class MarketBaselineRecord(ContractModel):
    event_id: str
    market_group_id: str
    market_id: str
    market_type: str
    period: str
    selection: str
    bookmaker: str
    source: str
    decimal_odds: float = Field(gt=1.0)
    market_probability_raw: float = Field(gt=0.0)
    market_probability_fair: float = Field(gt=0.0, lt=1.0)
    fair_odds: float = Field(gt=1.0)
    gross_ev_baseline: float
    decision_as_of: datetime
    max_input_observed_at: datetime
    payload_hash: str = Field(min_length=64, max_length=64)
    odds_snapshot_id: str | None = None


class WalkForwardFold(ContractModel):
    fold_index: int = Field(ge=0)
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_count: int = Field(gt=0)
    test_count: int = Field(gt=0)


class PayoutCostRule(ContractModel):
    rule_version: str
    jurisdiction: str
    market_scope: str
    effective_from: datetime
    effective_to: datetime | None = None
    payout_factor: float = Field(gt=0.0, le=1.0)
    stake_cost_rate: float = Field(ge=0.0)
    fixed_cost_per_unit_stake: float = Field(ge=0.0)
    source_ref: str
    verified_at: datetime
    production_allowed: bool = False
    notes: str | None = None


class MarketAnalysisRecord(ContractModel):
    event_id: str
    market_group_id: str
    market_id: str
    market_type: str
    period: str
    selection: str
    bookmaker: str
    source: str
    decimal_odds: float = Field(gt=1.0)
    market_probability_fair: float = Field(gt=0.0, lt=1.0)
    model_probability: float = Field(gt=0.0, lt=1.0)
    model_fair_odds: float = Field(gt=1.0)
    edge: float
    gross_ev: float
    net_ev: float
    uncertainty: float = Field(ge=0.0, le=1.0)
    data_quality: DataQualityStatus
    recommendation: Recommendation
    risk_blockers: tuple[str, ...] = ()
    is_model_validated: bool
    payout_cost_rule_version: str
    decision_as_of: datetime
    max_input_observed_at: datetime


class NBAMoneylineFeatureRecord(ContractModel):
    event_id: str
    feature_version: str = "nba-moneyline-features-v1"
    decision_as_of: datetime
    max_input_observed_at: datetime
    home_rating: float
    away_rating: float
    home_rest_days: int = Field(ge=0, le=14)
    away_rest_days: int = Field(ge=0, le=14)
    neutral_site: bool = False

    @model_validator(mode="after")
    def require_point_in_time_inputs(self) -> NBAMoneylineFeatureRecord:
        if self.max_input_observed_at > self.decision_as_of:
            raise ValueError("max_input_observed_at must not exceed decision_as_of")
        return self


class NBAMoneylineTrainingSample(ContractModel):
    features: NBAMoneylineFeatureRecord
    home_win: bool
    result_observed_at: datetime
    home_decimal_odds: float = Field(gt=1.0)
    away_decimal_odds: float = Field(gt=1.0)
    odds_observed_at: datetime
    closing_home_decimal_odds: float = Field(gt=1.0)
    closing_away_decimal_odds: float = Field(gt=1.0)
    closing_observed_at: datetime
    market_home_probability_fair: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def require_temporal_order(self) -> NBAMoneylineTrainingSample:
        if self.odds_observed_at > self.features.decision_as_of:
            raise ValueError("odds_observed_at must not exceed decision_as_of")
        if self.closing_observed_at < self.features.decision_as_of:
            raise ValueError("closing_observed_at must not precede decision_as_of")
        if self.result_observed_at < self.closing_observed_at:
            raise ValueError("result_observed_at must not precede closing_observed_at")
        return self


class WalkForwardEvaluationRecord(ContractModel):
    model_id: str
    model_version: str
    feature_version: str
    calibration_version: str = "uncalibrated-v1"
    test_window_start: datetime
    test_window_end: datetime
    fold_count: int = Field(gt=0)
    sample_count: int = Field(gt=0)
    bet_count: int = Field(ge=0)
    brier: float = Field(ge=0.0)
    log_loss: float = Field(ge=0.0)
    ece: float = Field(ge=0.0)
    market_brier: float = Field(ge=0.0)
    market_log_loss: float = Field(ge=0.0)
    market_ece: float = Field(ge=0.0)
    roi: float
    yield_rate: float
    clv: float | None = None
    max_drawdown: float = Field(ge=0.0)
    bootstrap_ci_low: float | None = None
    bootstrap_ci_high: float | None = None
    risk_of_ruin: float = Field(ge=0.0, le=1.0)
    recommendation: Recommendation
    is_model_validated: bool


class CalibrationRecord(ContractModel):
    calibration_version: str
    model_id: str
    model_version: str
    feature_version: str
    training_window_end: datetime
    calibration_window_start: datetime
    calibration_window_end: datetime
    fitted_at: datetime
    sample_count: int = Field(gt=0)
    intercept: float
    slope: float


class ModelValidationPolicy(ContractModel):
    policy_version: str
    min_sample_count: int = Field(gt=0)
    min_bet_count: int = Field(ge=0)
    min_brier_improvement: float = Field(ge=0.0)
    min_log_loss_improvement: float = Field(ge=0.0)
    max_ece: float = Field(ge=0.0)
    max_ece_vs_market_delta: float
    min_yield_rate: float
    min_clv: float
    max_drawdown: float = Field(ge=0.0)
    min_bootstrap_ci_low: float
    max_risk_of_ruin: float = Field(ge=0.0, le=1.0)
    allowed_evidence_tiers: tuple[EvidenceTier, ...]


class ModelValidationDecision(ContractModel):
    policy_version: str
    evidence_tier: EvidenceTier
    is_model_validated: bool
    blockers: tuple[str, ...]


class ResearchReadinessPolicy(ContractModel):
    policy_version: str
    research_key: str
    validation_policy_version: str
    decision_horizon_hours: int = Field(gt=0)
    min_train_size: int = Field(ge=2)
    test_size: int = Field(gt=0)
    calibration_size: int = Field(ge=0)
    bootstrap_iterations: int = Field(gt=0)


class ResearchReadinessAssessment(ContractModel):
    research_key: str
    checked_at: datetime
    readiness_policy_version: str
    validation_policy_version: str
    readiness_status: ResearchReadinessStatus
    dataset_fingerprint: str = Field(min_length=64, max_length=64)
    evaluation_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    candidate_event_count: int = Field(ge=0)
    decisive_event_count: int = Field(ge=0)
    usable_sample_count: int = Field(ge=0)
    decision_odds_covered_count: int = Field(ge=0)
    closing_odds_covered_count: int = Field(ge=0)
    decision_odds_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    closing_odds_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    skipped_missing_odds: int = Field(ge=0)
    skipped_non_decisive_result: int = Field(ge=0)
    skipped_feature_error: int = Field(ge=0)
    decision_horizon_hours: int = Field(gt=0)
    min_train_size: int = Field(ge=2)
    test_size: int = Field(gt=0)
    calibration_size: int = Field(ge=0)
    bootstrap_iterations: int = Field(gt=0)
    evaluation_min_usable_samples: int = Field(gt=0)
    evaluation_sample_capacity: int = Field(ge=0)
    validation_min_evaluation_samples: int = Field(gt=0)
    validation_min_usable_samples: int = Field(gt=0)
    remaining_to_evaluation: int = Field(ge=0)
    remaining_to_validation_samples: int = Field(ge=0)
    fold_count_capacity: int = Field(ge=0)
    ready_for_evaluation: bool
    validation_sample_ready: bool
    blockers: tuple[str, ...] = ()


class ResearchCycleRunRecord(ContractModel):
    research_run_id: str
    research_key: str
    readiness_policy_version: str
    validation_policy_version: str
    trigger_kind: str
    checked_at: datetime
    status: ResearchCycleStatus
    dataset_fingerprint: str = Field(min_length=64, max_length=64)
    evaluation_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    decision_horizon_hours: int = Field(gt=0)
    min_train_size: int = Field(ge=2)
    test_size: int = Field(gt=0)
    calibration_size: int = Field(ge=0)
    bootstrap_iterations: int = Field(gt=0)
    candidate_event_count: int = Field(ge=0)
    decisive_event_count: int = Field(ge=0)
    usable_sample_count: int = Field(ge=0)
    decision_odds_covered_count: int = Field(ge=0)
    closing_odds_covered_count: int = Field(ge=0)
    skipped_missing_odds: int = Field(ge=0)
    skipped_non_decisive_result: int = Field(ge=0)
    skipped_feature_error: int = Field(ge=0)
    evaluation_min_usable_samples: int = Field(gt=0)
    evaluation_sample_capacity: int = Field(ge=0)
    validation_min_evaluation_samples: int = Field(gt=0)
    validation_min_usable_samples: int = Field(gt=0)
    remaining_to_evaluation: int = Field(ge=0)
    remaining_to_validation_samples: int = Field(ge=0)
    fold_count_capacity: int = Field(ge=0)
    ready_for_evaluation: bool
    validation_sample_ready: bool
    blockers: tuple[str, ...] = ()
    evaluation_sample_count: int | None = Field(default=None, ge=0)
    validation_passed: bool | None = None
    report_relative_path: str | None = None
    model_promotion_performed: bool = False
    error_summary: str | None = None


class ResearchReadinessStatusRecord(ContractModel):
    assessment: ResearchReadinessAssessment
    latest_run: ResearchCycleRunRecord | None = None


class OperationalMonitoringPolicy(ContractModel):
    policy_version: str
    collection_stale_after_minutes: int = Field(gt=0)
    research_stale_after_minutes: int = Field(gt=0)
    budget_warning_fraction: float = Field(gt=0.0, le=1.0)


class OperationalMonitorSnapshotRecord(ContractModel):
    monitor_id: str
    policy_version: str
    trigger_kind: str
    checked_at: datetime
    severity: OperationalSeverity
    collection_run_id: str | None = None
    collection_run_status: str | None = None
    collection_age_minutes: float | None = Field(default=None, ge=0.0)
    research_run_id: str | None = None
    research_run_status: str | None = None
    research_age_minutes: float | None = Field(default=None, ge=0.0)
    requests_used: int | None = Field(default=None, ge=0)
    requests_remaining: int | None = Field(default=None, ge=0)
    local_monthly_budget: int | None = Field(default=None, gt=0)
    budget_usage_ratio: float | None = Field(default=None, ge=0.0)
    live_event_count: int = Field(ge=0)
    odds_snapshot_count: int = Field(ge=0)
    completed_result_count: int = Field(ge=0)
    past_event_without_result_count: int = Field(ge=0)
    readiness_status: ResearchReadinessStatus
    usable_sample_count: int = Field(ge=0)
    remaining_to_evaluation: int = Field(ge=0)
    remaining_to_validation_samples: int = Field(ge=0)
    decision_odds_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    closing_odds_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    odds_snapshot_delta: int | None = None
    completed_result_delta: int | None = None
    usable_sample_delta: int | None = None
    alerts: tuple[str, ...] = ()
