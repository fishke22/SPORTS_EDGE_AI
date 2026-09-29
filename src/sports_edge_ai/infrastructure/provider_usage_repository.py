from __future__ import annotations

from datetime import datetime

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import ProviderUsageSnapshot
from sports_edge_ai.infrastructure.db import connect, connect_readonly


def get_latest_provider_usage(
    *,
    provider_id: str,
    paths: ProjectPaths | None = None,
) -> ProviderUsageSnapshot | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT provider_id, observed_at, requests_remaining, requests_used,
                   requests_last, local_monthly_budget, endpoint_kind
            FROM provider_usage_snapshots
            WHERE provider_id = ?
            ORDER BY observed_at DESC, requests_used DESC NULLS LAST, endpoint_kind DESC
            LIMIT 1
            """,
            [provider_id],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return ProviderUsageSnapshot(
        provider_id=row[0],
        observed_at=row[1],
        requests_remaining=row[2],
        requests_used=row[3],
        requests_last=row[4],
        local_monthly_budget=row[5],
        endpoint_kind=row[6],
    )


def get_latest_provider_usage_for_endpoint(
    *,
    provider_id: str,
    endpoint_kind: str,
    paths: ProjectPaths | None = None,
) -> ProviderUsageSnapshot | None:
    connection = connect_readonly(paths)
    try:
        row = connection.execute(
            """
            SELECT provider_id, observed_at, requests_remaining, requests_used,
                   requests_last, local_monthly_budget, endpoint_kind
            FROM provider_usage_snapshots
            WHERE provider_id = ? AND endpoint_kind = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            [provider_id, endpoint_kind],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return ProviderUsageSnapshot(
        provider_id=row[0],
        observed_at=row[1],
        requests_remaining=row[2],
        requests_used=row[3],
        requests_last=row[4],
        local_monthly_budget=row[5],
        endpoint_kind=row[6],
    )


def assert_credit_budget(
    *,
    provider_id: str,
    local_monthly_budget: int,
    estimated_cost: int,
    paths: ProjectPaths,
) -> None:
    if local_monthly_budget <= 0:
        raise ValueError("local_monthly_budget must be positive")
    if estimated_cost <= 0:
        raise ValueError("estimated_cost must be positive")
    try:
        latest = get_latest_provider_usage(provider_id=provider_id, paths=paths)
    except FileNotFoundError:
        latest = None
    if latest is None or latest.requests_used is None:
        return
    if latest.requests_used + estimated_cost > local_monthly_budget:
        raise RuntimeError(
            "local free-tier credit budget would be exceeded: "
            f"used={latest.requests_used}, estimated_cost={estimated_cost}, "
            f"budget={local_monthly_budget}"
        )


def persist_provider_usage(
    snapshot: ProviderUsageSnapshot,
    *,
    paths: ProjectPaths,
) -> None:
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO provider_usage_snapshots
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                snapshot.provider_id,
                snapshot.observed_at,
                snapshot.requests_remaining,
                snapshot.requests_used,
                snapshot.requests_last,
                snapshot.local_monthly_budget,
                snapshot.endpoint_kind,
            ],
        )
    finally:
        connection.close()


def usage_snapshot_from_headers(
    *,
    provider_id: str,
    observed_at: datetime,
    requests_remaining: int | None,
    requests_used: int | None,
    requests_last: int | None,
    local_monthly_budget: int,
    endpoint_kind: str,
) -> ProviderUsageSnapshot:
    return ProviderUsageSnapshot(
        provider_id=provider_id,
        observed_at=observed_at,
        requests_remaining=requests_remaining,
        requests_used=requests_used,
        requests_last=requests_last,
        local_monthly_budget=local_monthly_budget,
        endpoint_kind=endpoint_kind,
    )
