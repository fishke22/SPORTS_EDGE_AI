from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sports_edge_ai.application.free_provider_pipeline import (
    normalize_current_nba_h2h,
    normalize_nba_scores,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    DataQualityStatus,
    ForwardCollectionRunRecord,
    ForwardCollectionStatusRecord,
)
from sports_edge_ai.infrastructure.db import connect_readonly, migrate
from sports_edge_ai.infrastructure.forward_collection_repository import (
    get_latest_forward_collection_run,
    persist_forward_collection_run,
)
from sports_edge_ai.infrastructure.provider_usage_repository import (
    get_latest_provider_usage,
    get_latest_provider_usage_for_endpoint,
)
from sports_edge_ai.infrastructure.providers.the_odds_api import (
    PROVIDER_ID,
    OddsApiTransport,
)
from sports_edge_ai.infrastructure.providers.the_odds_api_free import (
    fetch_current_nba_h2h,
    fetch_nba_scores,
)


def _require_aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _is_due(last_at: datetime | None, now: datetime, interval_minutes: int) -> bool:
    if interval_minutes <= 0:
        raise ValueError("collection intervals must be positive")
    if last_at is None:
        return True
    return now - last_at >= timedelta(minutes=interval_minutes)


def _safe_error_summary(exc: Exception, api_key: str) -> str:
    summary = f"{type(exc).__name__}: {exc}"
    normalized_key = api_key.strip()
    if normalized_key:
        summary = summary.replace(normalized_key, "[REDACTED]")
    return summary[:500]


def get_forward_collection_status(
    *,
    paths: ProjectPaths | None = None,
    checked_at: datetime | None = None,
    current_min_interval_minutes: int = 180,
    scores_min_interval_minutes: int = 720,
) -> ForwardCollectionStatusRecord:
    effective_paths = paths or ProjectPaths.discover()
    now = _require_aware(checked_at or datetime.now(UTC), "checked_at")
    current_usage = get_latest_provider_usage_for_endpoint(
        provider_id=PROVIDER_ID,
        endpoint_kind="current_nba_h2h",
        paths=effective_paths,
    )
    scores_usage = get_latest_provider_usage_for_endpoint(
        provider_id=PROVIDER_ID,
        endpoint_kind="nba_scores",
        paths=effective_paths,
    )
    latest_usage = get_latest_provider_usage(provider_id=PROVIDER_ID, paths=effective_paths)
    latest_run = get_latest_forward_collection_run(provider_id=PROVIDER_ID, paths=effective_paths)

    connection = connect_readonly(effective_paths)
    try:
        live_event_row = connection.execute(
            "SELECT count(DISTINCT event_id) FROM odds_snapshots WHERE source = 'the_odds_api'"
        ).fetchone()
        odds_snapshot_row = connection.execute(
            "SELECT count(*) FROM odds_snapshots WHERE source = 'the_odds_api'"
        ).fetchone()
        completed_result_row = connection.execute(
            """
            SELECT count(*)
            FROM event_results
            WHERE provider_id = ? AND completed = TRUE
            """,
            [PROVIDER_ID],
        ).fetchone()
        past_event_without_result_row = connection.execute(
            """
            SELECT count(*)
            FROM (
                SELECT DISTINCT event.event_id
                FROM canonical_events AS event
                JOIN odds_snapshots AS odds ON odds.event_id = event.event_id
                WHERE odds.source = 'the_odds_api'
                  AND event.scheduled_start < ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM event_results AS result
                      WHERE result.event_id = event.event_id
                        AND result.completed = TRUE
                  )
            )
            """,
            [now],
        ).fetchone()
        if (
            live_event_row is None
            or odds_snapshot_row is None
            or completed_result_row is None
            or past_event_without_result_row is None
        ):
            raise RuntimeError("collection status aggregate query returned no row")
        live_event_count = int(live_event_row[0])
        odds_snapshot_count = int(odds_snapshot_row[0])
        completed_result_count = int(completed_result_row[0])
        past_event_without_result_count = int(past_event_without_result_row[0])
        next_row = connection.execute(
            """
            SELECT min(event.scheduled_start)
            FROM canonical_events AS event
            JOIN odds_snapshots AS odds ON odds.event_id = event.event_id
            WHERE odds.source = 'the_odds_api'
              AND event.scheduled_start >= ?
            """,
            [now],
        ).fetchone()
    finally:
        connection.close()

    next_event_start = None if next_row is None else next_row[0]
    return ForwardCollectionStatusRecord(
        provider_id=PROVIDER_ID,
        checked_at=now,
        current_min_interval_minutes=current_min_interval_minutes,
        scores_min_interval_minutes=scores_min_interval_minutes,
        current_due=_is_due(
            None if current_usage is None else current_usage.observed_at,
            now,
            current_min_interval_minutes,
        ),
        scores_due=(
            past_event_without_result_count > 0
            and _is_due(
                None if scores_usage is None else scores_usage.observed_at,
                now,
                scores_min_interval_minutes,
            )
        ),
        last_current_at=None if current_usage is None else current_usage.observed_at,
        last_scores_at=None if scores_usage is None else scores_usage.observed_at,
        latest_run=latest_run,
        requests_used=None if latest_usage is None else latest_usage.requests_used,
        requests_remaining=None if latest_usage is None else latest_usage.requests_remaining,
        live_event_count=live_event_count,
        odds_snapshot_count=odds_snapshot_count,
        completed_result_count=completed_result_count,
        past_event_without_result_count=past_event_without_result_count,
        next_event_start=next_event_start,
    )


def run_forward_collection(
    *,
    api_key: str,
    paths: ProjectPaths | None = None,
    region: str = "us",
    local_monthly_budget: int = 450,
    current_min_interval_minutes: int = 180,
    scores_min_interval_minutes: int = 720,
    scores_days_from: int = 3,
    include_scores: bool = True,
    force_current: bool = False,
    force_scores: bool = False,
    trigger_kind: str = "MANUAL",
    started_at: datetime | None = None,
    current_transport: OddsApiTransport | None = None,
    scores_transport: OddsApiTransport | None = None,
) -> ForwardCollectionRunRecord:
    effective_paths = paths or ProjectPaths.discover()
    migrate(effective_paths)
    now = _require_aware(started_at or datetime.now(UTC), "started_at")
    before = get_latest_provider_usage(provider_id=PROVIDER_ID, paths=effective_paths)
    status_before = get_forward_collection_status(
        paths=effective_paths,
        checked_at=now,
        current_min_interval_minutes=current_min_interval_minutes,
        scores_min_interval_minutes=scores_min_interval_minutes,
    )
    current_due = force_current or status_before.current_due
    scores_due = include_scores and (force_scores or status_before.scores_due)
    run_id = uuid4().hex

    if not current_due and not scores_due:
        record = ForwardCollectionRunRecord(
            collection_run_id=run_id,
            provider_id=PROVIDER_ID,
            trigger_kind=trigger_kind,
            started_at=now,
            finished_at=datetime.now(UTC),
            status="SKIPPED",
            current_due=False,
            scores_due=False,
            current_attempted=False,
            scores_attempted=False,
            events_count=0,
            odds_count=0,
            results_count=0,
            unresolved_count=0,
            requests_used_before=None if before is None else before.requests_used,
            requests_used_after=None if before is None else before.requests_used,
            credits_spent=0,
            requests_remaining_after=None if before is None else before.requests_remaining,
        )
        persist_forward_collection_run(record, paths=effective_paths)
        return record

    current_attempted = False
    scores_attempted = False
    events_count = 0
    odds_count = 0
    results_count = 0
    unresolved_count = 0
    data_quality_status: DataQualityStatus | None = None
    mapping_rate: float | None = None
    credit_costs: list[int] = []
    completed_steps = 0
    try:
        if current_due:
            current_attempted = True
            current_fetch = fetch_current_nba_h2h(
                api_key=api_key,
                paths=effective_paths,
                fetched_at=now,
                region=region,
                local_monthly_budget=local_monthly_budget,
                transport=current_transport,
            )
            current = normalize_current_nba_h2h(current_fetch, paths=effective_paths)
            events_count = len(current.events)
            odds_count = len(current.odds)
            unresolved_count += len(current.unresolved_entities)
            data_quality_status = current.data_quality.status
            mapping_rate = current.data_quality.mapping_rate
            if current_fetch.quota.last_cost is not None:
                credit_costs.append(current_fetch.quota.last_cost)
            completed_steps += 1

        if scores_due:
            scores_attempted = True
            scores_fetch = fetch_nba_scores(
                api_key=api_key,
                paths=effective_paths,
                fetched_at=now,
                days_from=scores_days_from,
                local_monthly_budget=local_monthly_budget,
                transport=scores_transport,
            )
            scores = normalize_nba_scores(scores_fetch, paths=effective_paths)
            results_count = len(scores.results)
            unresolved_count += len(scores.unresolved_provider_events)
            if scores_fetch.quota.last_cost is not None:
                credit_costs.append(scores_fetch.quota.last_cost)
            completed_steps += 1
    except Exception as exc:
        after = get_latest_provider_usage(provider_id=PROVIDER_ID, paths=effective_paths)
        record = ForwardCollectionRunRecord(
            collection_run_id=run_id,
            provider_id=PROVIDER_ID,
            trigger_kind=trigger_kind,
            started_at=now,
            finished_at=datetime.now(UTC),
            status="FAILED" if completed_steps == 0 else "PARTIAL",
            current_due=current_due,
            scores_due=scores_due,
            current_attempted=current_attempted,
            scores_attempted=scores_attempted,
            events_count=events_count,
            odds_count=odds_count,
            results_count=results_count,
            unresolved_count=unresolved_count,
            data_quality_status=data_quality_status,
            mapping_rate=mapping_rate,
            requests_used_before=None if before is None else before.requests_used,
            requests_used_after=None if after is None else after.requests_used,
            credits_spent=sum(credit_costs) if credit_costs else None,
            requests_remaining_after=None if after is None else after.requests_remaining,
            error_summary=_safe_error_summary(exc, api_key),
        )
        persist_forward_collection_run(record, paths=effective_paths)
        raise

    after = get_latest_provider_usage(provider_id=PROVIDER_ID, paths=effective_paths)
    degraded = data_quality_status not in {None, DataQualityStatus.GREEN} or unresolved_count > 0
    record = ForwardCollectionRunRecord(
        collection_run_id=run_id,
        provider_id=PROVIDER_ID,
        trigger_kind=trigger_kind,
        started_at=now,
        finished_at=datetime.now(UTC),
        status="DEGRADED" if degraded else "SUCCESS",
        current_due=current_due,
        scores_due=scores_due,
        current_attempted=current_attempted,
        scores_attempted=scores_attempted,
        events_count=events_count,
        odds_count=odds_count,
        results_count=results_count,
        unresolved_count=unresolved_count,
        data_quality_status=data_quality_status,
        mapping_rate=mapping_rate,
        requests_used_before=None if before is None else before.requests_used,
        requests_used_after=None if after is None else after.requests_used,
        credits_spent=sum(credit_costs),
        requests_remaining_after=None if after is None else after.requests_remaining,
    )
    persist_forward_collection_run(record, paths=effective_paths)
    return record
