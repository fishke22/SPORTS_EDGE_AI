CREATE TABLE IF NOT EXISTS source_license_registry (
    license_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    data_type VARCHAR NOT NULL,
    license_name VARCHAR,
    commercial_allowed BOOLEAN,
    redistribution_allowed BOOLEAN,
    attribution_required BOOLEAN NOT NULL DEFAULT FALSE,
    automated_access_allowed BOOLEAN,
    credential_required BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at TIMESTAMPTZ NOT NULL,
    source_terms_ref VARCHAR,
    notes VARCHAR
);

CREATE TABLE IF NOT EXISTS provider_registry (
    provider_id VARCHAR PRIMARY KEY,
    provider_name VARCHAR NOT NULL,
    provider_type VARCHAR NOT NULL,
    official_url VARCHAR,
    api_version VARCHAR,
    auth_type VARCHAR,
    license_id VARCHAR,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    production_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    last_reviewed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS canonical_events (
    event_id VARCHAR PRIMARY KEY,
    schema_version VARCHAR NOT NULL,
    sport VARCHAR NOT NULL,
    league VARCHAR NOT NULL,
    season VARCHAR,
    home_team_id VARCHAR NOT NULL,
    away_team_id VARCHAR NOT NULL,
    scheduled_start TIMESTAMPTZ NOT NULL,
    venue_id VARCHAR,
    status VARCHAR NOT NULL,
    source_event_ids JSON NOT NULL,
    effective_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_markets (
    market_id VARCHAR PRIMARY KEY,
    schema_version VARCHAR NOT NULL,
    event_id VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    period VARCHAR NOT NULL,
    selection VARCHAR NOT NULL,
    line DOUBLE,
    market_rules_version VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_snapshot_id VARCHAR PRIMARY KEY,
    schema_version VARCHAR NOT NULL,
    event_id VARCHAR NOT NULL,
    market_id VARCHAR NOT NULL,
    bookmaker VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    decimal_odds DOUBLE NOT NULL CHECK (decimal_odds > 1.0),
    observed_at TIMESTAMPTZ NOT NULL,
    provider_timestamp TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL,
    is_live BOOLEAN NOT NULL DEFAULT FALSE,
    is_closing BOOLEAN NOT NULL DEFAULT FALSE,
    raw_source_ref VARCHAR NOT NULL,
    payload_hash VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_id VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    sport VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    training_window_start TIMESTAMPTZ NOT NULL,
    training_window_end TIMESTAMPTZ NOT NULL,
    validation_window_start TIMESTAMPTZ NOT NULL,
    validation_window_end TIMESTAMPTZ NOT NULL,
    feature_version VARCHAR NOT NULL,
    calibration_version VARCHAR NOT NULL,
    artifact_path VARCHAR NOT NULL,
    artifact_sha256 VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    status VARCHAR NOT NULL,
    metrics_json JSON NOT NULL,
    PRIMARY KEY (model_id, model_version)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id VARCHAR PRIMARY KEY,
    schema_version VARCHAR NOT NULL,
    event_id VARCHAR NOT NULL,
    market_id VARCHAR NOT NULL,
    model_id VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    feature_version VARCHAR NOT NULL,
    calibration_version VARCHAR NOT NULL,
    model_probability_raw DOUBLE NOT NULL,
    model_probability_calibrated DOUBLE NOT NULL,
    market_probability_raw DOUBLE,
    market_probability_fair DOUBLE,
    fair_odds DOUBLE NOT NULL,
    edge DOUBLE NOT NULL,
    gross_ev DOUBLE NOT NULL,
    net_ev DOUBLE NOT NULL,
    uncertainty DOUBLE NOT NULL,
    data_quality VARCHAR NOT NULL,
    recommendation VARCHAR NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    backtest_id VARCHAR PRIMARY KEY,
    model_id VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    sport VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    test_window_start TIMESTAMPTZ NOT NULL,
    test_window_end TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL,
    brier DOUBLE,
    log_loss DOUBLE,
    ece DOUBLE,
    roi DOUBLE,
    yield_rate DOUBLE,
    clv DOUBLE,
    max_drawdown DOUBLE,
    bootstrap_ci_low DOUBLE,
    bootstrap_ci_high DOUBLE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_trades (
    paper_trade_id VARCHAR PRIMARY KEY,
    prediction_id VARCHAR NOT NULL,
    event_id VARCHAR NOT NULL,
    market_id VARCHAR NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    odds_snapshot_id VARCHAR NOT NULL,
    odds_decimal DOUBLE NOT NULL CHECK (odds_decimal > 1.0),
    stake DOUBLE NOT NULL CHECK (stake > 0.0),
    status VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    settlement_rule_version VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
    settlement_id VARCHAR PRIMARY KEY,
    event_id VARCHAR NOT NULL,
    market_id VARCHAR NOT NULL,
    settlement_status VARCHAR NOT NULL,
    market_result VARCHAR,
    void_reason VARCHAR,
    payout_rule_version VARCHAR NOT NULL,
    tax_rule_version VARCHAR NOT NULL,
    gross_payout DOUBLE NOT NULL,
    net_payout DOUBLE NOT NULL,
    pnl DOUBLE NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    risk_assessment_id VARCHAR PRIMARY KEY,
    prediction_id VARCHAR NOT NULL,
    recommendation VARCHAR NOT NULL,
    data_quality VARCHAR NOT NULL,
    uncertainty DOUBLE NOT NULL,
    risk_blockers JSON NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS data_quality (
    data_quality_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    status VARCHAR NOT NULL,
    freshness_seconds BIGINT NOT NULL,
    missing_rate DOUBLE NOT NULL,
    duplicate_rate DOUBLE NOT NULL,
    mapping_rate DOUBLE NOT NULL,
    schema_version VARCHAR NOT NULL,
    message VARCHAR
);
