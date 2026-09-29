CREATE TABLE IF NOT EXISTS canonical_entities (
    entity_id VARCHAR PRIMARY KEY,
    entity_kind VARCHAR NOT NULL,
    sport VARCHAR,
    canonical_name VARCHAR NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_entity_mapping (
    provider_id VARCHAR NOT NULL,
    entity_kind VARCHAR NOT NULL,
    provider_entity_id VARCHAR NOT NULL,
    canonical_entity_id VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    confidence DOUBLE NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    resolution_method VARCHAR NOT NULL,
    PRIMARY KEY (provider_id, entity_kind, provider_entity_id)
);

INSERT OR IGNORE INTO source_license_registry VALUES (
    'license_synthetic_project',
    'synthetic_nba',
    'synthetic_fixture',
    'SPORTS_EDGE_AI project synthetic fixture',
    TRUE,
    TRUE,
    FALSE,
    TRUE,
    FALSE,
    '2026-09-28T00:00:00Z',
    'DATA_POLICY.md',
    'Project-authored synthetic data for tests; not real sportsbook data.'
);

INSERT OR IGNORE INTO provider_registry VALUES (
    'provider_synthetic_nba',
    'Synthetic NBA Fixture',
    'SYNTHETIC',
    NULL,
    'v1',
    'NONE',
    'license_synthetic_project',
    TRUE,
    FALSE,
    '2026-09-28T00:00:00Z'
);

INSERT OR IGNORE INTO canonical_entities VALUES
    ('SYNTH_HOME', 'TEAM', 'NBA', 'Synthetic Home', TRUE, '2026-09-28T00:00:00Z'),
    ('SYNTH_AWAY', 'TEAM', 'NBA', 'Synthetic Away', TRUE, '2026-09-28T00:00:00Z');

INSERT OR IGNORE INTO provider_entity_mapping VALUES
    (
        'provider_synthetic_nba',
        'TEAM',
        'SYNTH_HOME',
        'SYNTH_HOME',
        '2026-09-28T00:00:00Z',
        1.0,
        'SYNTHETIC_EXACT'
    ),
    (
        'provider_synthetic_nba',
        'TEAM',
        'SYNTH_AWAY',
        'SYNTH_AWAY',
        '2026-09-28T00:00:00Z',
        1.0,
        'SYNTHETIC_EXACT'
    );
