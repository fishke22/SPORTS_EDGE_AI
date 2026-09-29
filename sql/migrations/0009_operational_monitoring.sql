CREATE TABLE IF NOT EXISTS operational_monitor_snapshots (
    monitor_id VARCHAR PRIMARY KEY,
    policy_version VARCHAR NOT NULL,
    trigger_kind VARCHAR NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    severity VARCHAR NOT NULL,
    collection_run_id VARCHAR,
    collection_run_status VARCHAR,
    collection_age_minutes DOUBLE,
    research_run_id VARCHAR,
    research_run_status VARCHAR,
    research_age_minutes DOUBLE,
    requests_used BIGINT,
    requests_remaining BIGINT,
    local_monthly_budget BIGINT,
    budget_usage_ratio DOUBLE,
    live_event_count BIGINT NOT NULL,
    odds_snapshot_count BIGINT NOT NULL,
    completed_result_count BIGINT NOT NULL,
    past_event_without_result_count BIGINT NOT NULL,
    readiness_status VARCHAR NOT NULL,
    usable_sample_count BIGINT NOT NULL,
    remaining_to_evaluation BIGINT NOT NULL,
    remaining_to_validation_samples BIGINT NOT NULL,
    decision_odds_coverage_rate DOUBLE,
    closing_odds_coverage_rate DOUBLE,
    odds_snapshot_delta BIGINT,
    completed_result_delta BIGINT,
    usable_sample_delta BIGINT,
    alerts_json JSON NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operational_monitor_checked
ON operational_monitor_snapshots (checked_at);
