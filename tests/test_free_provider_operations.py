from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_edge_ai.application.entity_mapping import (
    approve_entity_mapping,
    get_mapping_review_summary,
    list_canonical_entities,
    list_entity_proposals,
    reject_entity_mapping,
)
from sports_edge_ai.application.free_provider_pipeline import (
    normalize_current_nba_h2h,
    normalize_nba_scores,
    propose_nba_participant_mappings,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import ProviderUsageSnapshot
from sports_edge_ai.infrastructure.db import connect, migrate
from sports_edge_ai.infrastructure.odds_repository import get_event_odds_as_of
from sports_edge_ai.infrastructure.provider_usage_repository import (
    get_latest_provider_usage,
    persist_provider_usage,
)
from sports_edge_ai.infrastructure.providers.the_odds_api import HttpResponse
from sports_edge_ai.infrastructure.providers.the_odds_api_free import (
    fetch_current_nba_h2h,
    fetch_nba_participants,
    fetch_nba_scores,
)
from sports_edge_ai.infrastructure.result_repository import get_latest_event_result

PROJECT_ROOT = Path(__file__).parents[1]
FIXTURES = PROJECT_ROOT / "fixtures" / "synthetic"


class FakeTransport:
    def __init__(
        self,
        body: bytes,
        *,
        used: int,
        remaining: int,
        last_cost: int,
    ) -> None:
        self.body = body
        self.used = used
        self.remaining = remaining
        self.last_cost = last_cost
        self.calls = 0
        self.url: str | None = None

    def get(self, *, url: str, timeout_seconds: float) -> HttpResponse:
        assert timeout_seconds > 0
        self.calls += 1
        self.url = url
        return HttpResponse(
            body=self.body,
            headers={
                "x-requests-used": str(self.used),
                "x-requests-remaining": str(self.remaining),
                "x-requests-last": str(self.last_cost),
            },
        )


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_migration_0006_seeds_free_capabilities_and_nba_teams(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    result = migrate(paths)

    assert result.current_version == "0009"
    connection = connect(paths)
    try:
        team_count = connection.execute(
            "SELECT count(*) FROM canonical_entities "
            "WHERE sport = 'NBA' AND entity_kind = 'TEAM' AND entity_id LIKE 'NBA_%'"
        ).fetchone()[0]
        capabilities = dict(
            connection.execute(
                """
                SELECT capability, capability_value
                FROM provider_capability_registry
                WHERE provider_id = 'provider_the_odds_api'
                """
            ).fetchall()
        )
    finally:
        connection.close()

    assert team_count == 30
    assert capabilities["starter_free_monthly_credits"] == "500"
    assert capabilities["current_nba_odds_free_plan"] == "true"
    assert capabilities["scores_free_plan"] == "true"
    assert capabilities["current_h2h_us_cost"] == "1"
    assert capabilities["scores_days_from_3_cost"] == "2"


def test_free_participants_current_odds_and_scores_end_to_end(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    participants_transport = FakeTransport(
        (FIXTURES / "the_odds_api_participants_contract.json").read_bytes(),
        used=1,
        remaining=499,
        last_cost=1,
    )
    participants = fetch_nba_participants(
        api_key="free-test-key",
        paths=paths,
        fetched_at=datetime(2026, 9, 28, 7, 0, tzinfo=UTC),
        transport=participants_transport,
    )
    proposals = propose_nba_participant_mappings(participants, paths=paths)

    assert {item.proposed_canonical_entity_id for item in proposals} == {
        "NBA_BOS",
        "NBA_NYK",
    }
    assert all(item.status == "PENDING" for item in proposals)
    listed = list_entity_proposals(
        provider_id="provider_the_odds_api",
        status="PENDING",
        paths=paths,
    )
    assert len(listed) == 2

    approve_entity_mapping(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="Boston Celtics",
        canonical_entity_id="NBA_BOS",
        review_note="exact official team name",
        paths=paths,
    )
    approve_entity_mapping(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="New York Knicks",
        canonical_entity_id="NBA_NYK",
        review_note="exact official team name",
        paths=paths,
    )

    odds_transport = FakeTransport(
        (FIXTURES / "the_odds_api_current_contract.json").read_bytes(),
        used=2,
        remaining=498,
        last_cost=1,
    )
    current = fetch_current_nba_h2h(
        api_key="free-test-key",
        paths=paths,
        fetched_at=datetime(2026, 9, 28, 7, 5, tzinfo=UTC),
        transport=odds_transport,
    )
    normalized = normalize_current_nba_h2h(current, paths=paths)

    assert normalized.data_quality.status.value == "GREEN"
    assert len(normalized.events) == 1
    assert len(normalized.odds) == 2
    event_id = normalized.events[0].event_id
    assert (
        get_event_odds_as_of(
            event_id=event_id,
            decision_as_of=datetime(2026, 9, 28, 7, 4, 59, tzinfo=UTC),
            paths=paths,
        )
        == ()
    )
    visible = get_event_odds_as_of(
        event_id=event_id,
        decision_as_of=datetime(2026, 9, 28, 7, 5, tzinfo=UTC),
        paths=paths,
    )
    assert {row.decimal_odds for row in visible} == {1.75, 2.15}

    scores_transport = FakeTransport(
        (FIXTURES / "the_odds_api_scores_contract.json").read_bytes(),
        used=4,
        remaining=496,
        last_cost=2,
    )
    scores = fetch_nba_scores(
        api_key="free-test-key",
        paths=paths,
        fetched_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
        days_from=3,
        transport=scores_transport,
    )
    score_result = normalize_nba_scores(scores, paths=paths)

    assert score_result.unresolved_provider_events == ()
    assert len(score_result.results) == 1
    result = get_latest_event_result(event_id=event_id, paths=paths)
    assert result is not None
    assert result.result_outcome == "HOME"
    assert result.home_score == 112
    assert result.away_score == 104

    usage = get_latest_provider_usage(
        provider_id="provider_the_odds_api",
        paths=paths,
    )
    assert usage is not None
    assert usage.requests_used == 4
    assert usage.requests_remaining == 496
    assert usage.endpoint_kind == "nba_scores"


def test_mapping_review_supports_reject_and_summary(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    participants = fetch_nba_participants(
        api_key="free-test-key",
        paths=paths,
        fetched_at=datetime(2026, 9, 28, 7, 0, tzinfo=UTC),
        transport=FakeTransport(
            (FIXTURES / "the_odds_api_participants_contract.json").read_bytes(),
            used=1,
            remaining=499,
            last_cost=1,
        ),
    )
    propose_nba_participant_mappings(participants, paths=paths)

    canonical = list_canonical_entities(
        entity_kind="TEAM", sport="NBA", entity_id_prefix="NBA_", paths=paths
    )
    assert len(canonical) == 30
    assert {row.entity_id for row in canonical} >= {"NBA_BOS", "NBA_NYK"}

    approve_entity_mapping(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="Boston Celtics",
        canonical_entity_id="NBA_BOS",
        review_note="first review",
        paths=paths,
    )
    rejected = reject_entity_mapping(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="Boston Celtics",
        review_note="rejected during second review",
        paths=paths,
    )

    assert rejected.status == "REJECTED"
    assert rejected.review_note == "rejected during second review"
    summary = get_mapping_review_summary(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        paths=paths,
    )
    assert summary.proposal_count == 2
    assert summary.pending_count == 1
    assert summary.approved_count == 0
    assert summary.rejected_count == 1
    assert summary.approved_mapping_count == 0
    assert summary.review_completion_rate == pytest.approx(0.5)

    connection = connect(paths)
    try:
        mapping = connection.execute(
            "SELECT canonical_entity_id FROM provider_entity_mapping "
            "WHERE provider_id = 'provider_the_odds_api' "
            "AND entity_kind = 'TEAM' AND provider_entity_id = 'Boston Celtics'"
        ).fetchone()
    finally:
        connection.close()
    assert mapping is None


def test_unapproved_mapping_blocks_current_canonical_odds(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    current = fetch_current_nba_h2h(
        api_key="free-test-key",
        paths=paths,
        fetched_at=datetime(2026, 9, 28, 7, 5, tzinfo=UTC),
        transport=FakeTransport(
            (FIXTURES / "the_odds_api_current_contract.json").read_bytes(),
            used=1,
            remaining=499,
            last_cost=1,
        ),
    )

    normalized = normalize_current_nba_h2h(current, paths=paths)

    assert normalized.data_quality.status.value == "RED"
    assert normalized.odds == ()
    assert normalized.unresolved_entities == ("Boston Celtics", "New York Knicks")


def test_local_free_credit_budget_blocks_request_before_transport(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    persist_provider_usage(
        ProviderUsageSnapshot(
            provider_id="provider_the_odds_api",
            observed_at=datetime(2026, 9, 28, 7, 0, tzinfo=UTC),
            requests_remaining=50,
            requests_used=450,
            requests_last=1,
            local_monthly_budget=450,
            endpoint_kind="current_nba_h2h",
        ),
        paths=paths,
    )
    transport = FakeTransport(b"[]", used=451, remaining=49, last_cost=1)

    with pytest.raises(RuntimeError, match="credit budget would be exceeded"):
        fetch_current_nba_h2h(
            api_key="free-test-key",
            paths=paths,
            fetched_at=datetime(2026, 9, 28, 8, 0, tzinfo=UTC),
            local_monthly_budget=450,
            transport=transport,
        )

    assert transport.calls == 0
