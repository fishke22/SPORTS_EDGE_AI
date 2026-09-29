from __future__ import annotations

import shutil
from pathlib import Path

from sports_edge_ai.application.doctor import run_system_doctor
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import migrate

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "portable"
    migrations = root / "sql" / "migrations"
    frontend = root / "frontend"
    migrations.mkdir(parents=True)
    frontend.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(PROJECT_ROOT / "uv.lock", root / "uv.lock")
    shutil.copy2(PROJECT_ROOT / "frontend" / "package-lock.json", frontend / "package-lock.json")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def test_doctor_reports_research_ready_but_production_gated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _portable_root(tmp_path)
    monkeypatch.chdir(paths.root)
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)
    migrate(paths)

    report = run_system_doctor(paths=paths)

    assert report.status == "DEGRADED"
    assert report.ready_for_research is True
    assert report.current_schema_version == "0009"
    assert report.expected_schema_version == "0009"
    assert report.credential_configured is False
    assert report.provider_production_allowed is False
    assert any(
        check.name == "provider_production_gate" and check.level == "WARN"
        for check in report.checks
    )


def test_doctor_treats_empty_dotenv_secret_as_not_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _portable_root(tmp_path)
    monkeypatch.chdir(paths.root)
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)
    (paths.root / ".env").write_text(
        "SPORTS_EDGE_THE_ODDS_API_KEY=\n",
        encoding="utf-8",
    )
    migrate(paths)

    report = run_system_doctor(paths=paths)

    assert report.credential_configured is False
    assert any(
        check.name == "the_odds_api_credential" and check.level == "WARN" for check in report.checks
    )


def test_doctor_fails_when_required_lockfile_is_missing(tmp_path: Path, monkeypatch) -> None:
    paths = _portable_root(tmp_path)
    monkeypatch.chdir(paths.root)
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)
    migrate(paths)
    (paths.root / "uv.lock").unlink()

    report = run_system_doctor(paths=paths)

    assert report.status == "FAIL"
    assert report.ready_for_research is False
    assert any(
        check.name == "required:uv.lock" and check.level == "FAIL" for check in report.checks
    )
