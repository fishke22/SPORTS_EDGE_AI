from pathlib import Path

from sports_edge_ai.common.root import ProjectPaths, resolve_project_root


def test_resolve_project_root_from_nested_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPORTS_EDGE_ROOT", raising=False)
    root = tmp_path / "portable-repo"
    nested = root / "src" / "package"
    nested.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")

    assert resolve_project_root(nested) == root.resolve()


def test_project_paths_keep_database_under_root(tmp_path: Path) -> None:
    root = tmp_path / "moved-repo"
    paths = ProjectPaths(root)

    assert paths.database == root / "state" / "sports_edge.duckdb"
    assert paths.database.relative_to(root) == Path("state") / "sports_edge.duckdb"
