from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from sports_edge_ai.application.entity_mapping import create_or_update_entity_proposal
from sports_edge_ai.application.synthetic_pipeline import ingest_synthetic_snapshot
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import (
    BacktestRecord,
    ModelRegistryRecord,
    ProviderUsageSnapshot,
)
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.model_repository import (
    persist_backtest_record,
    persist_model_registry_record,
)
from sports_edge_ai.infrastructure.provider_usage_repository import persist_provider_usage
from sports_edge_ai.interfaces.api import create_app

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _seed(paths: ProjectPaths) -> None:
    ingest_synthetic_snapshot(
        PROJECT_ROOT / "fixtures" / "synthetic" / "nba_moneyline_snapshot.json",
        paths=paths,
    )


def test_health_is_read_only_for_uninitialized_workspace(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    assert not paths.database.exists()
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "uninitialized",
        "database_ready": False,
        "schema_version": None,
    }
    assert not paths.database.exists()


def test_api_health_baseline_and_analysis(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    _seed(paths)
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "database_ready": True,
        "schema_version": "0009",
    }

    odds = client.get(
        "/api/v1/events/SYNTH_NBA_001/odds",
        params={"as_of": "2026-10-01T08:30:00Z"},
    )
    assert odds.status_code == 200
    assert len(odds.json()["odds"]) == 2

    baseline = client.get(
        "/api/v1/events/SYNTH_NBA_001/market-baseline",
        params={"as_of": "2026-10-01T08:30:00Z"},
    )
    assert baseline.status_code == 200
    assert len(baseline.json()["records"]) == 2

    analysis = client.post(
        "/api/v1/events/SYNTH_NBA_001/analysis",
        json={
            "as_of": "2026-10-01T08:30:00Z",
            "model_probabilities": {"HOME": 0.60, "AWAY": 0.40},
            "is_model_validated": False,
        },
    )
    assert analysis.status_code == 200
    by_selection = {row["selection"]: row for row in analysis.json()["records"]}
    assert by_selection["HOME"]["recommendation"] == "NO_VALIDATED_EDGE"
    assert by_selection["AWAY"]["recommendation"] == "NO_BET"


def test_api_rejects_invalid_probability_contract(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    _seed(paths)
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    response = client.post(
        "/api/v1/events/SYNTH_NBA_001/analysis",
        json={
            "as_of": "2026-10-01T08:30:00Z",
            "model_probabilities": {"HOME": 0.60},
        },
    )

    assert response.status_code == 400
    assert "must match market selections exactly" in response.json()["detail"]


def test_api_model_and_backtest_read_endpoints(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    created_at = datetime(2026, 9, 28, 12, tzinfo=UTC)
    registry = ModelRegistryRecord(
        model_id="api-model",
        model_version="v1",
        sport="NBA",
        market_type="MONEYLINE",
        training_window_start=datetime(2026, 1, 1, tzinfo=UTC),
        training_window_end=datetime(2026, 6, 1, tzinfo=UTC),
        validation_window_start=datetime(2026, 6, 2, tzinfo=UTC),
        validation_window_end=datetime(2026, 7, 1, tzinfo=UTC),
        feature_version="features-v1",
        calibration_version="cal-v1",
        artifact_path="models/api-model/v1/hash.json",
        artifact_sha256="0" * 64,
        created_at=created_at,
        status="RESEARCH_NOT_VALIDATED",
        metrics_json={"source": "test"},
    )
    backtest = BacktestRecord(
        backtest_id="api-backtest",
        model_id="api-model",
        model_version="v1",
        sport="NBA",
        market_type="MONEYLINE",
        test_window_start=datetime(2026, 6, 2, tzinfo=UTC),
        test_window_end=datetime(2026, 7, 1, tzinfo=UTC),
        sample_count=20,
        brier=0.2,
        log_loss=0.6,
        ece=0.04,
        roi=0.01,
        yield_rate=0.02,
        clv=0.01,
        max_drawdown=0.1,
        bootstrap_ci_low=-0.01,
        bootstrap_ci_high=0.04,
        created_at=created_at,
    )
    persist_model_registry_record(registry, paths=paths)
    persist_backtest_record(backtest, paths=paths)
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    model_response = client.get("/api/v1/models/api-model/v1")
    backtest_response = client.get("/api/v1/backtests/api-backtest")
    missing_response = client.get("/api/v1/backtests/missing")

    assert model_response.status_code == 200
    assert model_response.json()["model"]["status"] == "RESEARCH_NOT_VALIDATED"
    assert backtest_response.status_code == 200
    assert backtest_response.json()["backtest"]["sample_count"] == 20
    assert missing_response.status_code == 404


def test_api_provider_mapping_and_usage_reads(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    observed_at = datetime(2026, 9, 28, 7, 0, tzinfo=UTC)
    create_or_update_entity_proposal(
        provider_id="provider_the_odds_api",
        entity_kind="TEAM",
        provider_entity_id="Boston Celtics",
        provider_display_name="Boston Celtics",
        provider_object_id="par_bos",
        observed_at=observed_at,
        paths=paths,
    )
    persist_provider_usage(
        ProviderUsageSnapshot(
            provider_id="provider_the_odds_api",
            observed_at=observed_at,
            requests_remaining=488,
            requests_used=12,
            requests_last=1,
            local_monthly_budget=450,
            endpoint_kind="nba_participants",
        ),
        paths=paths,
    )
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    entities = client.get(
        "/api/v1/entities",
        params={"entity_kind": "TEAM", "sport": "NBA", "entity_id_prefix": "NBA_"},
    )
    proposals = client.get(
        "/api/v1/providers/provider_the_odds_api/entity-proposals",
        params={"status": "PENDING"},
    )
    summary = client.get("/api/v1/providers/provider_the_odds_api/mapping-summary/TEAM")
    usage = client.get("/api/v1/providers/provider_the_odds_api/usage")

    assert entities.status_code == 200
    assert len(entities.json()["records"]) == 30
    assert proposals.status_code == 200
    assert proposals.json()["records"][0]["provider_entity_id"] == "Boston Celtics"
    assert summary.status_code == 200
    assert summary.json()["pending_count"] == 1
    assert usage.status_code == 200
    assert usage.json()["usage"]["requests_used"] == 12


def test_api_forward_collection_status_is_read_only(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    future = datetime(2099, 1, 1, tzinfo=UTC)
    persist_provider_usage(
        ProviderUsageSnapshot(
            provider_id="provider_the_odds_api",
            observed_at=future,
            requests_remaining=490,
            requests_used=10,
            requests_last=1,
            local_monthly_budget=450,
            endpoint_kind="current_nba_h2h",
        ),
        paths=paths,
    )
    persist_provider_usage(
        ProviderUsageSnapshot(
            provider_id="provider_the_odds_api",
            observed_at=future,
            requests_remaining=488,
            requests_used=12,
            requests_last=2,
            local_monthly_budget=450,
            endpoint_kind="nba_scores",
        ),
        paths=paths,
    )
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    response = client.get("/api/v1/providers/provider_the_odds_api/collection-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_due"] is False
    assert payload["scores_due"] is False
    assert payload["requests_used"] == 12
    assert payload["latest_run"] is None
    assert payload["live_event_count"] == 0


def test_api_research_readiness_is_read_only_and_fail_closed(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    response = client.get("/api/v1/research/nba/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["assessment"]["readiness_status"] == "NOT_READY"
    assert payload["assessment"]["usable_sample_count"] == 0
    assert payload["assessment"]["evaluation_min_usable_samples"] == 180
    assert payload["assessment"]["validation_min_usable_samples"] == 360
    assert payload["latest_run"] is None


def test_api_operational_status_is_read_only_and_fail_closed(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    response = client.get("/api/v1/operations/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["severity"] == "WARN"
    assert "collection_heartbeat_missing" in payload["alerts"]
    assert "research_heartbeat_missing" in payload["alerts"]
    assert payload["readiness_status"] == "NOT_READY"


def test_api_paper_and_result_reads_are_safe_when_empty(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path)
    migrate(paths)
    client = TestClient(create_app(paths=paths, serve_frontend=False))

    result = client.get("/api/v1/events/UNKNOWN_EVENT/result")
    portfolio = client.get("/api/v1/paper/portfolio")

    assert result.status_code == 200
    assert result.json() == {"found": False, "result": None}
    assert portfolio.status_code == 200
    assert portfolio.json()["open_count"] == 0
    assert portfolio.json()["settled_count"] == 0
    assert portfolio.json()["void_count"] == 0
    assert portfolio.json()["total_stake"] == 0.0
    assert portfolio.json()["realized_pnl"] == 0.0
