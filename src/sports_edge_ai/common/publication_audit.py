from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["BLOCKER", "WARNING", "INFO"]
MAX_PUBLIC_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AuditFinding:
    severity: Severity
    code: str
    message: str
    path: str | None = None


def _git_tracked(root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def _metadata_first(
    metadata: importlib.metadata.PackageMetadata,
    key: str,
) -> str | None:
    values = metadata.get_all(key) or []
    return values[0] if values else None


def _license_text(metadata: importlib.metadata.PackageMetadata) -> str:
    expression = _metadata_first(metadata, "License-Expression")
    if expression:
        return expression
    license_name = _metadata_first(metadata, "License")
    if license_name:
        return license_name
    classifiers = metadata.get_all("Classifier") or []
    license_classifiers = [item for item in classifiers if "License ::" in item]
    return " | ".join(license_classifiers) or "UNKNOWN"


def _python_dependency_findings() -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    strong_copyleft = re.compile(r"\b(AGPL|GPL(?:-|\b))(?!.*Lesser)", re.IGNORECASE)
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda item: (_metadata_first(item.metadata, "Name") or "").lower(),
    ):
        name = _metadata_first(distribution.metadata, "Name") or "UNKNOWN"
        license_text = _license_text(distribution.metadata)
        if strong_copyleft.search(license_text):
            findings.append(
                AuditFinding(
                    "WARNING",
                    "PYTHON_COPYLEFT_REVIEW",
                    f"{name}: {license_text}",
                )
            )
        elif license_text == "UNKNOWN":
            findings.append(
                AuditFinding(
                    "WARNING",
                    "PYTHON_LICENSE_UNKNOWN",
                    f"{name}: license metadata unavailable",
                )
            )
    return findings


def _node_dependency_findings(root: Path) -> list[AuditFinding]:
    node_modules = root / "frontend" / "node_modules"
    if not node_modules.is_dir():
        return [
            AuditFinding(
                "WARNING",
                "NODE_MODULES_NOT_INSTALLED",
                "Run npm --prefix frontend ci before publication audit for dependency metadata.",
            )
        ]
    findings: list[AuditFinding] = []
    strong_copyleft = re.compile(r"\b(AGPL|GPL(?:-|\b))(?!.*LGPL)", re.IGNORECASE)
    package_jsons: list[Path] = []
    for entry in node_modules.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name.startswith("@"):
            for scoped_package in entry.iterdir():
                candidate = scoped_package / "package.json"
                if candidate.is_file():
                    package_jsons.append(candidate)
        else:
            candidate = entry / "package.json"
            if candidate.is_file():
                package_jsons.append(candidate)

    for package_json in sorted(package_jsons):
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = str(payload.get("name") or package_json.parent.name)
        license_value = payload.get("license", "UNKNOWN")
        if isinstance(license_value, dict):
            license_text = str(license_value.get("type", "UNKNOWN"))
        else:
            license_text = str(license_value)
        if strong_copyleft.search(license_text):
            findings.append(
                AuditFinding("WARNING", "NODE_COPYLEFT_REVIEW", f"{name}: {license_text}")
            )
        elif license_text == "UNKNOWN":
            findings.append(
                AuditFinding(
                    "WARNING",
                    "NODE_LICENSE_UNKNOWN",
                    f"{name}: license metadata unavailable",
                )
            )
    return findings


def run_audit(root: Path) -> dict[str, object]:
    root = root.resolve()
    tracked = _git_tracked(root)
    findings: list[AuditFinding] = []

    required_files = (
        ".github/workflows/ci.yml",
        "LICENSE",
        "README.md",
        "DATA_POLICY.md",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/PUBLICATION_CHECKLIST.md",
    )
    for relative in required_files:
        if relative not in tracked:
            findings.append(
                AuditFinding(
                    "BLOCKER",
                    "REQUIRED_PUBLICATION_FILE_MISSING",
                    "Required publication governance file is not tracked.",
                    relative,
                )
            )

    forbidden_prefixes = (
        "data/bronze/",
        "data/silver/",
        "data/gold/",
        "state/",
        "backups/",
        "logs/",
        "models/",
        "reports/",
    )
    allowed_gitkeep = {
        "data/bronze/.gitkeep",
        "data/silver/.gitkeep",
        "data/gold/.gitkeep",
        "state/.gitkeep",
        "backups/.gitkeep",
        "logs/.gitkeep",
        "models/.gitkeep",
        "reports/.gitkeep",
    }
    secret_assignment = re.compile(
        r"(?im)^(?:[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)"
        r"[ \t]*=[ \t]*(\S[^\r\n]*)$"
    )
    token_patterns = (
        re.compile(r"sk-proj-[A-Za-z0-9_-]{16,}"),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{20,}"),
    )
    github_action_use = re.compile(r"(?m)^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)")
    full_commit_sha = re.compile(r"^[0-9a-f]{40}$")
    absolute_windows = re.compile(r"(?i)\b[A-Z]:\\(?:Users|Program Files|sport)\\")
    text_suffixes = {
        ".py",
        ".ps1",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".md",
        ".txt",
        ".ts",
        ".tsx",
        ".css",
        ".html",
        ".sql",
        ".example",
    }

    for relative in tracked:
        path = root / relative
        normalized = relative.replace("\\", "/")
        if normalized == ".env":
            findings.append(
                AuditFinding("BLOCKER", "REAL_ENV_TRACKED", "Do not publish .env.", relative)
            )
        if any(normalized.startswith(prefix) for prefix in forbidden_prefixes):
            if normalized not in allowed_gitkeep:
                findings.append(
                    AuditFinding(
                        "BLOCKER",
                        "RUNTIME_OR_DATA_FILE_TRACKED",
                        "Runtime data/state/model/report/backup must not be published by default.",
                        relative,
                    )
                )
        if path.is_file() and path.stat().st_size > MAX_PUBLIC_FILE_BYTES:
            findings.append(
                AuditFinding(
                    "BLOCKER",
                    "LARGE_TRACKED_FILE",
                    f"Tracked file exceeds {MAX_PUBLIC_FILE_BYTES} bytes.",
                    relative,
                )
            )
        is_env_text = path.name == ".env" or path.name.startswith(".env.")
        if not path.is_file() or (path.suffix.lower() not in text_suffixes and not is_env_text):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if normalized.startswith(".github/workflows/") and path.suffix.lower() in {".yml", ".yaml"}:
            for action, reference in github_action_use.findall(text):
                if action.startswith("./"):
                    continue
                if not full_commit_sha.fullmatch(reference):
                    findings.append(
                        AuditFinding(
                            "BLOCKER",
                            "UNPINNED_GITHUB_ACTION",
                            "GitHub Action must be pinned to a full commit SHA: "
                            f"{action}@{reference}",
                            relative,
                        )
                    )
        if secret_assignment.search(text):
            findings.append(
                AuditFinding(
                    "BLOCKER",
                    "NONEMPTY_SECRET_ASSIGNMENT",
                    "Tracked text contains a non-empty secret-like environment assignment.",
                    relative,
                )
            )
        if any(pattern.search(text) for pattern in token_patterns):
            findings.append(
                AuditFinding(
                    "BLOCKER",
                    "TOKEN_PATTERN_FOUND",
                    "Tracked text contains a credential-like token pattern.",
                    relative,
                )
            )
        if absolute_windows.search(text) and normalized not in {
            "SPORTS_EDGE_AI_PROJECT_SOURCES/SPORTS_EDGE_AI_PROJECT_SOURCES.md",
            "docs/DEV_HANDOFF.md",
        }:
            findings.append(
                AuditFinding(
                    "BLOCKER",
                    "HARDCODED_WINDOWS_PATH",
                    "Tracked source/document contains a machine-specific Windows path.",
                    relative,
                )
            )

    findings.extend(_python_dependency_findings())
    findings.extend(_node_dependency_findings(root))

    try:
        history = subprocess.run(
            ["git", "rev-list", "--all", "--count"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_count = int(history.stdout.strip() or "0")
    except (subprocess.CalledProcessError, ValueError):
        commit_count = -1
        findings.append(
            AuditFinding(
                "WARNING",
                "GIT_HISTORY_AUDIT_UNAVAILABLE",
                "Could not determine Git history size.",
            )
        )
    if commit_count == 0:
        findings.append(
            AuditFinding(
                "INFO",
                "GIT_HISTORY_EMPTY",
                "Repository has no commits, so there is no prior history to secret-scan.",
            )
        )

    blockers = [finding for finding in findings if finding.severity == "BLOCKER"]
    warnings = [finding for finding in findings if finding.severity == "WARNING"]
    return {
        "schema_version": "publication-audit-v1",
        "ready_for_user_review": not blockers,
        "public_push_performed": False,
        "tracked_file_count": len(tracked),
        "git_commit_count": commit_count,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "findings": [asdict(finding) for finding in findings],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[3])
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write the JSON result under reports/audits/.",
    )
    args = parser.parse_args()
    result = run_audit(args.root)
    if args.write_report:
        report_dir = args.root / "reports" / "audits"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "publication_audit.json"
        report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["blocker_count"] else 0)


if __name__ == "__main__":
    main()
