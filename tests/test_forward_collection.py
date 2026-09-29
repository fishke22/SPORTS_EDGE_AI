from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sports_edge_ai.application.entity_mapping import approve_entity_mapping
from sports_edge_ai.application.forward_collection import (
    get_forward_collection_status,
    run_forward_collection,
)
from sports_edge_ai.application.free_provider_pipeline import propose_nba_participant_mappings
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.forward_collection_repository import (
    get_latest_forward_collection_run,
)
from sports_edge_ai.infrastructure.providers.the_odds_api import HttpResponse
from sports_edge_ai.infrastructure.providers.the_odds_api_free import fetch_nba_participants

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

    def get(self, *, url: str, timeout_seconds: float) -> HttpResponse:
        assert url
        assert timeout_seconds > 0
        self.calls += 1
        return HttpResponse(
            body=self.body,
            headers={
                "x-requests-used": str(self.used),
                "x-requests-remaining": str(self.remaining),
                "x-requests-last": str(self.last_cost),
            },
        )


class FailingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *, url: str, timeout_seconds: float) -> HttpResponse:
        assert url
        assert timeout_seconds > 0
        self.calls += 1
        raise RuntimeError("synthetic transport failure test-key")


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _approve_fixture_teams(paths: ProjectPaths) -> None:
    migrate(paths)
    participants = fetch_nba_participants(
        api_key="test-key",
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
    approve_entity_mapping(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="Boston Celtics",
        canonical_entity_id="NBA_BOS",
        review_note="test mapping",
        paths=paths,
    )
    approve_entity_mapping(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="New York Knicks",
        canonical_entity_id="NBA_NYK",
        review_note="test mapping",
        paths=paths,
    )


def test_forward_collection_respects_due_intervals_and_records_usage(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    _approve_fixture_teams(paths)
    started = datetime(2026, 9, 28, 7, 5, tzinfo=UTC)
    current_transport = FakeTransport(
        (FIXTURES / "the_odds_api_current_contract.json").read_bytes(),
        used=2,
        remaining=498,
        last_cost=1,
    )
    scores_transport = FakeTransport(
        b"[]",
        used=4,
        remaining=496,
        last_cost=2,
    )

    first = run_forward_collection(
        api_key="test-key",
        paths=paths,
        started_at=started,
        current_transport=current_transport,
        scores_transport=scores_transport,
    )

    assert first.status == "SUCCESS"
    assert first.current_attempted is True
    assert first.scores_attempted is False
    assert first.events_count == 1
    assert first.odds_count == 2
    assert first.results_count == 0
    assert first.credits_spent == 1
    assert first.requests_used_after == 2
    assert current_transport.calls == 1
    assert scores_transport.calls == 0

    skip_current = FakeTransport(b"[]", used=5, remaining=495, last_cost=1)
    skip_scores = FakeTransport(b"[]", used=6, remaining=494, last_cost=2)
    skipped = run_forward_collection(
        api_key="test-key",
        paths=paths,
        started_at=started + timedelta(hours=1),
        current_transport=skip_current,
        scores_transport=skip_scores,
    )

    assert skipped.status == "SKIPPED"
    assert skipped.credits_spent == 0
    assert skip_current.calls == 0
    assert skip_scores.calls == 0

    status = get_forward_collection_status(
        paths=paths,
        checked_at=started + timedelta(hours=1),
    )
    assert status.current_due is False
    assert status.scores_due is False
    assert status.live_event_count == 1
    assert status.odds_snapshot_count == 2
    assert status.completed_result_count == 0
    assert status.latest_run is not None
    assert status.latest_run.status == "SKIPPED"

    later_current = FakeTransport(
        (FIXTURES / "the_odds_api_current_contract.json").read_bytes(),
        used=5,
        remaining=495,
        last_cost=1,
    )
    later_scores = FakeTransport(b"[]", used=7, remaining=493, last_cost=2)
    later = run_forward_collection(
        api_key="test-key",
        paths=paths,
        started_at=started + timedelta(hours=3, minutes=1),
        current_transport=later_current,
        scores_transport=later_scores,
    )

    assert later.status == "SUCCESS"
    assert later.current_attempted is True
    assert later.scores_attempted is False
    assert later.credits_spent == 1
    assert later_current.calls == 1
    assert later_scores.calls == 0

    score_only_current = FakeTransport(b"[]", used=6, remaining=494, last_cost=1)
    score_only_scores = FakeTransport(
        (FIXTURES / "the_odds_api_scores_contract.json").read_bytes(),
        used=7,
        remaining=493,
        last_cost=2,
    )
    score_only = run_forward_collection(
        api_key="test-key",
        paths=paths,
        started_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
        current_min_interval_minutes=1440,
        current_transport=score_only_current,
        scores_transport=score_only_scores,
    )

    assert score_only.status == "SUCCESS"
    assert score_only.current_attempted is False
    assert score_only.scores_attempted is True
    assert score_only.results_count == 1
    assert score_only.credits_spent == 2
    assert score_only_current.calls == 0
    assert score_only_scores.calls == 1


def test_forward_collection_persists_failed_run_before_reraising(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    _approve_fixture_teams(paths)
    transport = FailingTransport()

    with pytest.raises(RuntimeError, match="synthetic transport failure"):
        run_forward_collection(
            api_key="test-key",
            paths=paths,
            include_scores=False,
            started_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
            current_transport=transport,
        )

    assert transport.calls == 1
    latest = get_latest_forward_collection_run(
        provider_id="provider_the_odds_api",
        paths=paths,
    )
    assert latest is not None
    assert latest.status == "FAILED"
    assert latest.current_attempted is True
    assert latest.scores_attempted is False
    assert latest.error_summary is not None
    assert "synthetic transport failure" in latest.error_summary
    assert "test-key" not in latest.error_summary
    assert "[REDACTED]" in latest.error_summary
