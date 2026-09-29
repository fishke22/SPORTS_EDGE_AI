CREATE TABLE IF NOT EXISTS raw_objects (
    payload_sha256 VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    relative_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    object_bytes BIGINT NOT NULL,
    public_export_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    ingest_run_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    payload_sha256 VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    row_count BIGINT NOT NULL,
    manifest_relative_path VARCHAR NOT NULL,
    success BOOLEAN NOT NULL,
    error_code VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_ingest_runs_provider_observed
ON ingest_runs(provider, observed_at);
