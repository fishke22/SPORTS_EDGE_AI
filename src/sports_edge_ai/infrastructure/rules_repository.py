from __future__ import annotations

from datetime import datetime

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import PayoutCostRule
from sports_edge_ai.infrastructure.db import connect_readonly


def get_payout_cost_rule(
    *,
    rule_version: str,
    decision_as_of: datetime,
    paths: ProjectPaths | None = None,
) -> PayoutCostRule:
    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise ValueError("decision_as_of must be timezone-aware")

    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT rule_version, jurisdiction, market_scope, effective_from,
                   effective_to, payout_factor, stake_cost_rate,
                   fixed_cost_per_unit_stake, source_ref, verified_at,
                   production_allowed, notes
            FROM payout_cost_rules
            WHERE rule_version = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR ? < effective_to)
            """,
            [rule_version, decision_as_of, decision_as_of],
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise ValueError(f"payout/cost rule {rule_version!r} is not effective at decision_as_of")

    return PayoutCostRule(
        rule_version=row[0],
        jurisdiction=row[1],
        market_scope=row[2],
        effective_from=row[3],
        effective_to=row[4],
        payout_factor=float(row[5]),
        stake_cost_rate=float(row[6]),
        fixed_cost_per_unit_stake=float(row[7]),
        source_ref=row[8],
        verified_at=row[9],
        production_allowed=bool(row[10]),
        notes=row[11],
    )
