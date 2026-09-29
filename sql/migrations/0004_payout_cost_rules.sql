CREATE TABLE IF NOT EXISTS payout_cost_rules (
    rule_version VARCHAR PRIMARY KEY,
    jurisdiction VARCHAR NOT NULL,
    market_scope VARCHAR NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    payout_factor DOUBLE NOT NULL CHECK (payout_factor > 0.0 AND payout_factor <= 1.0),
    stake_cost_rate DOUBLE NOT NULL CHECK (stake_cost_rate >= 0.0),
    fixed_cost_per_unit_stake DOUBLE NOT NULL CHECK (fixed_cost_per_unit_stake >= 0.0),
    source_ref VARCHAR NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    production_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    notes VARCHAR
);

INSERT OR IGNORE INTO payout_cost_rules VALUES (
    'synthetic-zero-cost-v1',
    'SYNTHETIC',
    'ALL',
    '2026-01-01T00:00:00Z',
    NULL,
    1.0,
    0.0,
    0.0,
    'DATA_POLICY.md',
    '2026-09-28T00:00:00Z',
    FALSE,
    'Synthetic testing rule only; not a Taiwan Sports Lottery payout or tax rule.'
);
