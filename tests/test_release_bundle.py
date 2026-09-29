from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from sports_edge_ai.common.release_bundle import build_release_bundle
from sports_edge_ai.common.root import ProjectPaths


def _release_repo(tmp_path: Path) -> ProjectPaths:
    root = tmp_path / "release-repo"
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "data" / "bronze").mkdir(parents=True)
    (root / "backups").mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sports-edge-ai"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("safe source\n", encoding="utf-8")
    (root / "frontend" / "dist" / "index.html").write_text(
        "<!doctype html><title>SPORTS_EDGE_AI</title>",
        encoding="utf-8",
    )
    (root / "frontend" / "dist" / "assets" / "app.js").write_text(
        "console.log('safe');",
        encoding="utf-8",
    )
    (root / "data" / "bronze" / "licensed.json").write_text(
        '{"provider":"raw"}',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", ".sports-edge-root", "pyproject.toml", "README.md"],
        cwd=root,
        check=True,
    )
    return ProjectPaths(root)


def test_release_bundle_is_deterministic_and_excludes_untracked_raw(tmp_path: Path) -> None:
    paths = _release_repo(tmp_path)

    first = build_release_bundle(paths=paths, enforce_publication_audit=False)
    second = build_release_bundle(paths=paths, enforce_publication_audit=False)

    assert first.sha256 == second.sha256
    assert first.manifest_sha256 == second.manifest_sha256
    archive_path = paths.root / first.relative_path
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "README.md" in names
        assert "frontend/dist/index.html" in names
        assert "frontend/dist/assets/app.js" in names
        assert "data/bronze/licensed.json" not in names
        manifest = json.loads(archive.read("release-manifest.json"))
    assert manifest["includes_runtime_state"] is False
    assert manifest["includes_provider_raw_data"] is False


def test_release_bundle_rejects_output_outside_project_root(tmp_path: Path) -> None:
    paths = _release_repo(tmp_path)

    with pytest.raises(ValueError, match="PROJECT_ROOT"):
        build_release_bundle(
            paths=paths,
            output_dir=tmp_path / "outside",
            enforce_publication_audit=False,
        )
