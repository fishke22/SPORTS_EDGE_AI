from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from click.utils import strip_ansi
from typer.testing import CliRunner

from sports_edge_ai.cli import app
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.domain.schemas import ProviderUsageSnapshot
from sports_edge_ai.infrastructure.provider_usage_repository import persist_provider_usage

PROJECT_ROOT = Path(__file__).parents[1]
RUNNER = CliRunner()


def _portable_root(tmp_path: Path) -> Path:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return root


def test_repo_smoke_runs_without_credentials_or_persistent_state(monkeypatch) -> None:
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)

    result = RUNNER.invoke(app, ["repo-smoke"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["mode"] == "OFFLINE_SYNTHETIC_EPHEMERAL"
    assert payload["schema_version"] == "0009"
    assert payload["network_required"] is False
    assert payload["credentials_required"] is False
    assert payload["persistent_state_required"] is False
    assert payload["validated_edge_claimed"] is False
    assert "EDGE" not in payload["recommendations"]
    assert "NO_VALIDATED_EDGE" in payload["recommendations"]
    assert payload["baseline_odds"] == {"AWAY": 2.1, "HOME": 1.8}


def test_checkpoint_backend_smoke_cli_is_reference_only() -> None:
    result = RUNNER.invoke(app, ["checkpoint-backend-smoke"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["backend_id"] == "local-filesystem-reference-v1"
    assert payload["remote_live_eligible"] is False
    assert "NO_REMOTE_ACCESS" in payload["blockers"]
    assert "REFERENCE_ONLY_BACKEND" in payload["blockers"]
    assert payload["generation"] == payload["checkpoint_sha256"]


def test_zero_cost_status_and_operational_checkpoint_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)
    assert RUNNER.invoke(app, ["init-db"]).exit_code == 0

    before = RUNNER.invoke(app, ["zero-cost-status"])
    created = RUNNER.invoke(app, ["build-operational-checkpoint"])
    after = RUNNER.invoke(app, ["zero-cost-status"])

    assert before.exit_code == 0
    before_payload = json.loads(before.output)
    assert before_payload["status"] == "LIVE_REMOTE_BLOCKED"
    assert before_payload["paid_services_allowed"] is False
    assert before_payload["automatic_billing_allowed"] is False
    assert before_payload["public_repo_is_state_authority"] is False
    assert before_payload["github_actions_artifact_is_state_authority"] is False
    assert before_payload["remote_live_collection_ready"] is False
    assert before_payload["checkpoint_available"] is False
    assert "NO_VERIFIED_ZERO_COST_DURABLE_BACKEND" in before_payload["blockers"]
    assert "PRIVATE_DURABLE_CHECKPOINT_STORAGE" in before_payload["required_capabilities"]
    assert "AUTO_UPGRADE_TO_PAID" in before_payload["forbidden_fallbacks"]
    assert (
        "DELETE_POINT_IN_TIME_EVIDENCE_TO_FIT_FREE_QUOTA"
        in before_payload["forbidden_fallbacks"]
    )

    assert created.exit_code == 0
    created_payload = json.loads(created.output)
    assert created_payload["source_schema_version"] == "0009"
    assert created_payload["public_export_allowed"] is False
    assert created_payload["secret_transport"] is False
    relative = created_payload["relative_path"]
    assert (root / relative).is_file()

    verified = RUNNER.invoke(app, ["verify-operational-checkpoint", relative])
    assert verified.exit_code == 0
    verified_payload = json.loads(verified.output)
    assert verified_payload["source_schema_version"] == "0009"
    assert verified_payload["includes_raw_data"] is True
    assert verified_payload["public_export_allowed"] is False

    assert after.exit_code == 0
    after_payload = json.loads(after.output)
    assert after_payload["status"] == "LIVE_REMOTE_BLOCKED"
    assert after_payload["checkpoint_available"] is True
    assert after_payload["latest_checkpoint_relative_path"] == relative


def test_free_provider_cli_requires_secret_credential(tmp_path: Path, monkeypatch) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)

    result = RUNNER.invoke(app, ["ingest-the-odds-api-current"])

    assert result.exit_code != 0
    assert "SPORTS_EDGE_THE_ODDS_API_KEY is required" in result.output


def test_configure_odds_api_key_hides_and_persists_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)
    secret = "live-test-secret-123"

    result = RUNNER.invoke(
        app,
        ["configure-odds-api-key"],
        input=f"{secret}\n{secret}\n",
    )

    assert result.exit_code == 0
    assert secret not in result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["credential_nonempty"] is True
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert f"SPORTS_EDGE_THE_ODDS_API_KEY={secret}" in env_text


def test_collect_forward_skips_when_not_due_without_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    monkeypatch.setenv("SPORTS_EDGE_THE_ODDS_API_KEY", "test-key")
    assert RUNNER.invoke(app, ["init-db"]).exit_code == 0
    paths = ProjectPaths(root)
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

    run = RUNNER.invoke(app, ["collect-forward"])
    status = RUNNER.invoke(app, ["collection-status"])

    assert run.exit_code == 0
    run_payload = json.loads(run.output)
    assert run_payload["status"] == "SKIPPED"
    assert run_payload["credits_spent"] == 0
    assert status.exit_code == 0
    status_payload = json.loads(status.output)
    assert status_payload["current_due"] is False
    assert status_payload["scores_due"] is False
    assert status_payload["latest_run"]["status"] == "SKIPPED"


def test_research_readiness_and_cycle_are_fail_closed_when_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    assert RUNNER.invoke(app, ["init-db"]).exit_code == 0

    before = RUNNER.invoke(app, ["research-readiness"])
    cycle = RUNNER.invoke(app, ["research-cycle", "--trigger-kind", "TEST"])
    after = RUNNER.invoke(app, ["research-readiness"])

    assert before.exit_code == 0
    before_payload = json.loads(before.output)
    assert before_payload["assessment"]["readiness_status"] == "NOT_READY"
    assert before_payload["assessment"]["usable_sample_count"] == 0
    assert before_payload["assessment"]["evaluation_min_usable_samples"] == 180
    assert before_payload["latest_run"] is None

    assert cycle.exit_code == 0
    cycle_payload = json.loads(cycle.output)
    assert cycle_payload["status"] == "NOT_READY"
    assert cycle_payload["model_promotion_performed"] is False

    assert after.exit_code == 0
    after_payload = json.loads(after.output)
    assert after_payload["latest_run"]["status"] == "NOT_READY"


def test_operational_monitor_and_status_are_fail_closed_when_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    assert RUNNER.invoke(app, ["init-db"]).exit_code == 0

    monitor = RUNNER.invoke(app, ["ops-monitor", "--trigger-kind", "TEST"])
    status = RUNNER.invoke(app, ["ops-status"])

    assert monitor.exit_code == 0
    monitor_payload = json.loads(monitor.output)
    assert monitor_payload["severity"] == "WARN"
    assert "collection_heartbeat_missing" in monitor_payload["alerts"]
    assert "research_heartbeat_missing" in monitor_payload["alerts"]
    assert monitor_payload["trigger_kind"] == "TEST"

    assert status.exit_code == 0
    status_payload = json.loads(status.output)
    assert status_payload["severity"] == "WARN"


def test_local_research_cli_returns_insufficient_data(tmp_path: Path, monkeypatch) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))

    init = RUNNER.invoke(app, ["init-db"])
    result = RUNNER.invoke(
        app,
        [
            "local-nba-research",
            "--min-train-size",
            "4",
            "--test-size",
            "2",
            "--calibration-size",
            "2",
            "--bootstrap-iterations",
            "20",
        ],
    )

    assert init.exit_code == 0
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "INSUFFICIENT_DATA"
    assert payload["sample_count"] == 0


def test_backup_cli_creates_portable_archive(tmp_path: Path, monkeypatch) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    assert RUNNER.invoke(app, ["init-db"]).exit_code == 0

    result = RUNNER.invoke(app, ["backup-state"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    relative = Path(payload["relative_path"])
    assert not relative.is_absolute()
    assert (root / relative).is_file()
    assert payload["sha256"]
    assert payload["file_count"] >= 1


def test_restore_cli_requires_force(tmp_path: Path, monkeypatch) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(root))
    assert RUNNER.invoke(app, ["init-db"]).exit_code == 0
    backup = json.loads(RUNNER.invoke(app, ["backup-state"]).output)

    result = RUNNER.invoke(app, ["restore-state", backup["relative_path"]])

    assert result.exit_code != 0
    assert "rerun with --force" in strip_ansi(result.output)
