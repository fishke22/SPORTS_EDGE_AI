from __future__ import annotations

import subprocess
from pathlib import Path

from sports_edge_ai.common.publication_audit import run_audit


def _init_public_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    required = (
        ".github/workflows/ci.yml",
        "LICENSE",
        "README.md",
        "DATA_POLICY.md",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/PUBLICATION_CHECKLIST.md",
    )
    for relative in required:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == ".github/workflows/ci.yml":
            path.write_text(
                "steps:\n  - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n",
                encoding="utf-8",
            )
        else:
            path.write_text("public-safe\n", encoding="utf-8")
    (root / ".env.example").write_text(
        "SERVICE_API_KEY=\nSERVICE_REGION=us\n",
        encoding="utf-8",
    )
    for relative in (
        "data/bronze/.gitkeep",
        "data/silver/.gitkeep",
        "data/gold/.gitkeep",
        "state/.gitkeep",
        "backups/.gitkeep",
        "logs/.gitkeep",
        "models/.gitkeep",
        "reports/.gitkeep",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def test_publication_audit_accepts_clean_tracked_source(tmp_path: Path) -> None:
    root = _init_public_repo(tmp_path)

    result = run_audit(root)

    assert result["blocker_count"] == 0
    assert result["ready_for_user_review"] is True
    assert result["public_push_performed"] is False


def test_publication_audit_blocks_real_env_and_nonempty_secret(tmp_path: Path) -> None:
    root = _init_public_repo(tmp_path)
    (root / ".env").write_text("SERVICE_API_KEY=real-secret-value\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env"], cwd=root, check=True)

    result = run_audit(root)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["ready_for_user_review"] is False
    assert "REAL_ENV_TRACKED" in codes
    assert "NONEMPTY_SECRET_ASSIGNMENT" in codes


def test_publication_audit_blocks_unpinned_github_action(tmp_path: Path) -> None:
    root = _init_public_repo(tmp_path)
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.write_text("steps:\n  - uses: actions/checkout@v7\n", encoding="utf-8")
    subprocess.run(["git", "add", str(workflow.relative_to(root))], cwd=root, check=True)

    result = run_audit(root)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["ready_for_user_review"] is False
    assert "UNPINNED_GITHUB_ACTION" in codes
