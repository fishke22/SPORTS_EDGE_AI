CREATE TABLE IF NOT EXISTS provider_capability_registry (
    provider_id VARCHAR NOT NULL,
    capability VARCHAR NOT NULL,
    capability_value VARCHAR NOT NULL,
    evidence_ref VARCHAR NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (provider_id, capability)
);

INSERT OR IGNORE INTO source_license_registry VALUES (
    'license_the_odds_api_terms_20260831',
    'the_odds_api',
    'sports_market_odds',
    'The Odds API Terms and Conditions (2026-08-31)',
    TRUE,
    FALSE,
    FALSE,
    TRUE,
    TRUE,
    '2026-09-28T00:00:00Z',
    'https://the-odds-api.com/terms-and-conditions.html',
    'Storage, analytical dashboards, derived values and ML use are permitted; '
    'standalone raw-data resale/repackaging/redistribution is prohibited.'
);

INSERT OR IGNORE INTO provider_registry VALUES (
    'provider_the_odds_api',
    'The Odds API',
    'ODDS_API',
    'https://the-odds-api.com/',
    'v4',
    'QUERY_API_KEY',
    'license_the_odds_api_terms_20260831',
    TRUE,
    FALSE,
    '2026-09-28T00:00:00Z'
);

INSERT OR IGNORE INTO provider_capability_registry VALUES
    (
        'provider_the_odds_api',
        'historical_featured_odds',
        'true',
        'https://the-odds-api.com/liveapi/guides/v4/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'historical_snapshot_semantics',
        'closest_snapshot_lte_requested',
        'https://the-odds-api.com/liveapi/guides/v4/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'historical_snapshot_granularity_since_2022_09',
        '5_minutes',
        'https://the-odds-api.com/historical-odds-data/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'historical_plan_requirement',
        'paid_plan',
        'https://the-odds-api.com/liveapi/guides/v4/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'paid_rate_limit_rps',
        '30',
        'https://the-odds-api.com/guide/rate-limit.html',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'raw_redistribution_allowed',
        'false',
        'https://the-odds-api.com/terms-and-conditions.html',
        '2026-09-28T00:00:00Z'
    );
