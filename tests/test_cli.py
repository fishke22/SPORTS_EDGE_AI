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
