from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sports_edge_ai.common.root import ROOT_MARKER, ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.infrastructure.db import current_schema_version, latest_migration_version
from sports_edge_ai.infrastructure.provider_repository import get_provider_access_policy
from sports_edge_ai.infrastructure.providers.the_odds_api import PROVIDER_ID

DoctorLevel = Literal["OK", "WARN", "FAIL"]


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    level: DoctorLevel
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: str
    ready_for_research: bool
    project_root: str
    current_schema_version: str | None
    expected_schema_version: str | None
    credential_configured: bool
    provider_production_allowed: bool | None
    checks: tuple[DoctorCheck, ...]


def run_system_doctor(*, paths: ProjectPaths | None = None) -> DoctorReport:
    effective_paths = paths or ProjectPaths.discover()
    checks: list[DoctorCheck] = []

    required_files = (
        effective_paths.root / ROOT_MARKER,
        effective_paths.root / "pyproject.toml",
        effective_paths.root / "uv.lock",
        effective_paths.root / "frontend" / "package-lock.json",
    )
    for required in required_files:
        relative = required.relative_to(effective_paths.root).as_posix()
        checks.append(
            DoctorCheck(
                name=f"required:{relative}",
                level="OK" if required.is_file() else "FAIL",
                detail="present" if required.is_file() else "missing",
            )
        )

    expected_schema = latest_migration_version(effective_paths)
    current_schema = current_schema_version(effective_paths)
    if current_schema is None:
        checks.append(DoctorCheck("database", "WARN", "uninitialized"))
    elif current_schema != expected_schema:
        checks.append(
            DoctorCheck(
                "database",
                "FAIL",
                f"schema {current_schema} != expected {expected_schema}",
            )
        )
    else:
        checks.append(DoctorCheck("database", "OK", f"schema {current_schema}"))

    frontend_index = effective_paths.root / "frontend" / "dist" / "index.html"
    checks.append(
        DoctorCheck(
            "frontend_build",
            "OK" if frontend_index.is_file() else "WARN",
            "built assets present"
            if frontend_index.is_file()
            else "run npm --prefix frontend run build",
        )
    )

    settings = Settings()
    credential_configured = bool(
        settings.the_odds_api_key is not None
        and settings.the_odds_api_key.get_secret_value().strip()
    )
    checks.append(
        DoctorCheck(
            "the_odds_api_credential",
            "OK" if credential_configured else "WARN",
            "configured"
            if credential_configured
            else "not configured; live provider calls disabled",
        )
    )

    provider_production_allowed: bool | None = None
    if current_schema == expected_schema and current_schema is not None:
        try:
            provider_policy = get_provider_access_policy(
                provider_id=PROVIDER_ID,
                paths=effective_paths,
            )
            provider_production_allowed = provider_policy.production_allowed
            checks.append(
                DoctorCheck(
                    "provider_production_gate",
                    "OK" if provider_policy.production_allowed else "WARN",
                    (
                        "production allowed"
                        if provider_policy.production_allowed
                        else "research-only / production_allowed=false"
                    ),
                )
            )
        except (FileNotFoundError, ValueError) as exc:
            checks.append(DoctorCheck("provider_production_gate", "FAIL", str(exc)))

    has_fail = any(check.level == "FAIL" for check in checks)
    has_warn = any(check.level == "WARN" for check in checks)
    ready_for_research = (
        not has_fail and current_schema == expected_schema and current_schema is not None
    )
    status = "FAIL" if has_fail else ("DEGRADED" if has_warn else "OK")
    return DoctorReport(
        status=status,
        ready_for_research=ready_for_research,
        project_root=str(effective_paths.root),
        current_schema_version=current_schema,
        expected_schema_version=expected_schema,
        credential_configured=credential_configured,
        provider_production_allowed=provider_production_allowed,
        checks=tuple(checks),
    )
