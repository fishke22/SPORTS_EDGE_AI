CREATE TABLE IF NOT EXISTS provider_usage_snapshots (
    provider_id VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    requests_remaining BIGINT,
    requests_used BIGINT,
    requests_last BIGINT,
    local_monthly_budget BIGINT NOT NULL,
    endpoint_kind VARCHAR NOT NULL,
    PRIMARY KEY (provider_id, observed_at, endpoint_kind)
);

CREATE TABLE IF NOT EXISTS provider_entity_proposals (
    provider_id VARCHAR NOT NULL,
    entity_kind VARCHAR NOT NULL,
    provider_entity_id VARCHAR NOT NULL,
    provider_display_name VARCHAR NOT NULL,
    provider_object_id VARCHAR,
    proposed_canonical_entity_id VARCHAR,
    proposal_method VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ,
    review_note VARCHAR,
    PRIMARY KEY (provider_id, entity_kind, provider_entity_id)
);

CREATE TABLE IF NOT EXISTS event_results (
    event_result_id VARCHAR PRIMARY KEY,
    event_id VARCHAR,
    provider_id VARCHAR NOT NULL,
    provider_event_id VARCHAR NOT NULL,
    home_score BIGINT,
    away_score BIGINT,
    result_outcome VARCHAR,
    completed BOOLEAN NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    provider_timestamp TIMESTAMPTZ,
    raw_source_ref VARCHAR NOT NULL,
    payload_hash VARCHAR NOT NULL
);

ALTER TABLE settlements ADD COLUMN IF NOT EXISTS paper_trade_id VARCHAR;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS bookmaker VARCHAR;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS source VARCHAR;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS odds_snapshot_id VARCHAR;

INSERT OR IGNORE INTO provider_capability_registry VALUES
    (
        'provider_the_odds_api',
        'starter_free_monthly_credits',
        '500',
        'https://the-odds-api.com/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'current_nba_odds_free_plan',
        'true',
        'https://the-odds-api.com/sports/nba-odds.html',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'current_h2h_us_cost',
        '1',
        'https://the-odds-api.com/liveapi/guides/v4/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'scores_free_plan',
        'true',
        'https://the-odds-api.com/sports/nba-odds.html',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'scores_days_from_3_cost',
        '2',
        'https://the-odds-api.com/liveapi/guides/v4/',
        '2026-09-28T00:00:00Z'
    ),
    (
        'provider_the_odds_api',
        'participants_cost',
        '1',
        'https://the-odds-api.com/liveapi/guides/v4/',
        '2026-09-28T00:00:00Z'
    );

INSERT OR IGNORE INTO payout_cost_rules VALUES (
    'paper-decimal-zero-cost-v1',
    'PAPER',
    'NBA_MONEYLINE',
    '2026-01-01T00:00:00Z',
    NULL,
    1.0,
    0.0,
    0.0,
    'docs/OPERATIONS.md',
    '2026-09-28T00:00:00Z',
    FALSE,
    'Paper-research accounting only; not a Taiwan Sports Lottery payout or tax rule.'
);

INSERT OR IGNORE INTO canonical_entities VALUES
    ('NBA_ATL', 'TEAM', 'NBA', 'Atlanta Hawks', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_BOS', 'TEAM', 'NBA', 'Boston Celtics', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_BKN', 'TEAM', 'NBA', 'Brooklyn Nets', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_CHA', 'TEAM', 'NBA', 'Charlotte Hornets', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_CHI', 'TEAM', 'NBA', 'Chicago Bulls', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_CLE', 'TEAM', 'NBA', 'Cleveland Cavaliers', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_DAL', 'TEAM', 'NBA', 'Dallas Mavericks', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_DEN', 'TEAM', 'NBA', 'Denver Nuggets', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_DET', 'TEAM', 'NBA', 'Detroit Pistons', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_GSW', 'TEAM', 'NBA', 'Golden State Warriors', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_HOU', 'TEAM', 'NBA', 'Houston Rockets', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_IND', 'TEAM', 'NBA', 'Indiana Pacers', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_LAC', 'TEAM', 'NBA', 'LA Clippers', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_LAL', 'TEAM', 'NBA', 'Los Angeles Lakers', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_MEM', 'TEAM', 'NBA', 'Memphis Grizzlies', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_MIA', 'TEAM', 'NBA', 'Miami Heat', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_MIL', 'TEAM', 'NBA', 'Milwaukee Bucks', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_MIN', 'TEAM', 'NBA', 'Minnesota Timberwolves', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_NOP', 'TEAM', 'NBA', 'New Orleans Pelicans', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_NYK', 'TEAM', 'NBA', 'New York Knicks', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_OKC', 'TEAM', 'NBA', 'Oklahoma City Thunder', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_ORL', 'TEAM', 'NBA', 'Orlando Magic', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_PHI', 'TEAM', 'NBA', 'Philadelphia 76ers', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_PHX', 'TEAM', 'NBA', 'Phoenix Suns', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_POR', 'TEAM', 'NBA', 'Portland Trail Blazers', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_SAC', 'TEAM', 'NBA', 'Sacramento Kings', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_SAS', 'TEAM', 'NBA', 'San Antonio Spurs', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_TOR', 'TEAM', 'NBA', 'Toronto Raptors', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_UTA', 'TEAM', 'NBA', 'Utah Jazz', TRUE, '2026-09-28T00:00:00Z'),
    ('NBA_WAS', 'TEAM', 'NBA', 'Washington Wizards', TRUE, '2026-09-28T00:00:00Z');
