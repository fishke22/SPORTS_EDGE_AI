from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest
from typer.testing import CliRunner

from sports_edge_ai.application.the_odds_api_pipeline import normalize_historical_nba_h2h
from sports_edge_ai.cli import app
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect, migrate
from sports_edge_ai.infrastructure.odds_repository import get_event_odds_as_of
from sports_edge_ai.infrastructure.providers import the_odds_api as odds_api_module
from sports_edge_ai.infrastructure.providers.the_odds_api import (
    HttpResponse,
    ProviderRequestError,
    UrllibOddsApiTransport,
    fetch_historical_nba_h2h_snapshot,
    parse_historical_odds_payload,
)

PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE = PROJECT_ROOT / "fixtures" / "synthetic" / "the_odds_api_historical_contract.json"


class FakeTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requested_url: str | None = None

    def get(self, *, url: str, timeout_seconds: float) -> HttpResponse:
        assert timeout_seconds > 0.0
        self.requested_url = url
        return HttpResponse(
            body=self.body,
            headers={
                "x-requests-remaining": "499",
                "x-requests-used": "1",
                "x-requests-last": "10",
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


def _fetch(tmp_path: Path):
    paths = _portable_root(tmp_path)
    transport = FakeTransport(FIXTURE.read_bytes())
    result = fetch_historical_nba_h2h_snapshot(
        api_key="secret-test-key",
        requested_at=datetime(2026, 9, 1, 12, 2, tzinfo=UTC),
        ingested_at=datetime(2026, 9, 1, 12, 3, tzinfo=UTC),
        paths=paths,
        transport=transport,
    )
    return paths, transport, result


def _seed_fixture_mappings(paths: ProjectPaths) -> None:
    migrate(paths)
    connection = connect(paths)
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO canonical_entities VALUES
                ('EX_HOME', 'TEAM', 'NBA', 'Example Home', TRUE, '2026-09-01T00:00:00Z'),
                ('EX_AWAY', 'TEAM', 'NBA', 'Example Away', TRUE, '2026-09-01T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO provider_entity_mapping VALUES
                (
                    'provider_the_odds_api', 'TEAM', 'Example Home', 'EX_HOME',
                    '2026-09-01T00:00:00Z', 1.0, 'TEST_EXACT'
                ),
                (
                    'provider_the_odds_api', 'TEAM', 'Example Away', 'EX_AWAY',
                    '2026-09-01T00:00:00Z', 1.0, 'TEST_EXACT'
                )
            """
        )
    finally:
        connection.close()


def test_cli_requires_secret_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "portable"
    root.mkdir()
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    monkeypatch.chdir(root)
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)

    result = CliRunner().invoke(
        app,
        ["ingest-the-odds-api-historical", "2026-09-01T12:02:00Z"],
    )

    assert result.exit_code != 0
    assert "SPORTS_EDGE_THE_ODDS_API_KEY is required" in result.output
    assert "--api-key" not in result.output


def test_http_error_does_not_leak_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "super-secret-api-key"

    def fail_urlopen(*_args, **_kwargs):
        raise HTTPError(
            f"https://example.invalid/?apiKey={secret}",
            429,
            "Too Many Requests",
            {"Retry-After": "2"},
            None,
        )

    monkeypatch.setattr(odds_api_module, "urlopen", fail_urlopen)

    with pytest.raises(ProviderRequestError) as exc_info:
        UrllibOddsApiTransport().get(
            url=f"https://example.invalid/?apiKey={secret}",
            timeout_seconds=1.0,
        )

    message = str(exc_info.value)
    assert "HTTP 429" in message
    assert "retry_after=2" in message
    assert secret not in message


def test_historical_payload_rejects_future_snapshot() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["timestamp"] = "2026-09-01T12:03:00Z"

    with pytest.raises(RuntimeError, match="exceeds requested_at"):
        parse_historical_odds_payload(
            json.dumps(payload).encode(),
            requested_at=datetime(2026, 9, 1, 12, 2, tzinfo=UTC),
        )


def test_market_update_after_requested_time_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["data"][0]["bookmakers"][0]["markets"][0]["last_update"] = "2026-09-01T12:03:00Z"
    paths = _portable_root(tmp_path)
    fetch = fetch_historical_nba_h2h_snapshot(
        api_key="secret-test-key",
        requested_at=datetime(2026, 9, 1, 12, 2, tzinfo=UTC),
        ingested_at=datetime(2026, 9, 1, 12, 3, tzinfo=UTC),
        paths=paths,
        transport=FakeTransport(json.dumps(payload).encode()),
    )
    _seed_fixture_mappings(paths)

    with pytest.raises(RuntimeError, match="provider market timestamp exceeds requested_at"):
        normalize_historical_nba_h2h(fetch, paths=paths)


def test_requested_time_after_commence_is_not_treated_as_pregame(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    fetch = fetch_historical_nba_h2h_snapshot(
        api_key="secret-test-key",
        requested_at=datetime(2026, 9, 2, 0, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 9, 2, 0, 2, tzinfo=UTC),
        paths=paths,
        transport=FakeTransport(FIXTURE.read_bytes()),
    )
    _seed_fixture_mappings(paths)

    normalized = normalize_historical_nba_h2h(fetch, paths=paths)

    assert normalized.events == ()
    assert normalized.odds == ()
    assert normalized.data_quality.status.value == "YELLOW"
    assert normalized.data_quality.missing_rate == 1.0


def test_fetch_writes_immutable_bronze_without_exposing_key(tmp_path: Path) -> None:
    paths, transport, result = _fetch(tmp_path)

    assert result.snapshot.timestamp == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    assert result.quota.remaining == 499
    assert result.quota.last_cost == 10
    assert transport.requested_url is not None
    assert "secret-test-key" in transport.requested_url
    assert "secret-test-key" not in repr(result)
    assert (paths.root / result.bronze.relative_path).is_file()
    manifest = (paths.root / result.bronze.manifest_relative_path).read_text(encoding="utf-8")
    assert "secret-test-key" not in manifest
    assert '"public_export_allowed": false' in manifest


def test_unresolved_mapping_persists_red_quality_but_no_canonical_odds(
    tmp_path: Path,
) -> None:
    paths, _, fetch = _fetch(tmp_path)

    normalized = normalize_historical_nba_h2h(fetch, paths=paths)

    assert normalized.odds == ()
    assert normalized.data_quality.status.value == "RED"
    assert normalized.data_quality.mapping_rate == 0.0
    assert normalized.unresolved_entities == ("Example Away", "Example Home")
    connection = connect(paths)
    try:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM raw_objects WHERE provider = 'the_odds_api'),
                (SELECT count(*) FROM odds_snapshots WHERE source = 'the_odds_api')
            """
        ).fetchone()
    finally:
        connection.close()
    assert counts == (1, 0)


def test_mapped_snapshot_normalizes_to_point_in_time_canonical_odds(
    tmp_path: Path,
) -> None:
    paths, _, fetch = _fetch(tmp_path)
    _seed_fixture_mappings(paths)

    normalized = normalize_historical_nba_h2h(fetch, paths=paths)

    assert len(normalized.events) == 1
    assert len(normalized.markets) == 2
    assert len(normalized.odds) == 2
    assert normalized.data_quality.status.value == "GREEN"
    assert normalized.data_quality.mapping_rate == 1.0
    assert all((paths.root / relative).is_file() for relative in normalized.silver_paths)
    event_id = normalized.events[0].event_id

    before_market_update = get_event_odds_as_of(
        event_id=event_id,
        decision_as_of=datetime(2026, 9, 1, 12, 0, 15, tzinfo=UTC),
        paths=paths,
    )
    after_market_update = get_event_odds_as_of(
        event_id=event_id,
        decision_as_of=datetime(2026, 9, 1, 12, 1, tzinfo=UTC),
        paths=paths,
    )

    assert before_market_update == ()
    assert {row.decimal_odds for row in after_market_update} == {1.8, 2.1}
    assert all(
        row.observed_at == datetime(2026, 9, 1, 12, 0, 30, tzinfo=UTC)
        for row in after_market_update
    )
