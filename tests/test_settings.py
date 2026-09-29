from __future__ import annotations

from pathlib import Path

from sports_edge_ai.common.settings import Settings


def _root(tmp_path: Path, name: str, secret: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    (root / ".env").write_text(
        f"SPORTS_EDGE_THE_ODDS_API_KEY={secret}\n",
        encoding="utf-8",
    )
    return root


def test_settings_load_dotenv_from_resolved_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    selected = _root(tmp_path, "selected", "selected-secret")
    other = _root(tmp_path, "other", "other-secret")
    monkeypatch.chdir(other)
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(selected))
    monkeypatch.delenv("SPORTS_EDGE_THE_ODDS_API_KEY", raising=False)

    settings = Settings()

    assert settings.paths.root == selected.resolve()
    assert settings.the_odds_api_key is not None
    assert settings.the_odds_api_key.get_secret_value() == "selected-secret"


def test_process_environment_overrides_project_dotenv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    selected = _root(tmp_path, "selected", "dotenv-secret")
    monkeypatch.setenv("SPORTS_EDGE_ROOT", str(selected))
    monkeypatch.setenv("SPORTS_EDGE_THE_ODDS_API_KEY", "process-secret")

    settings = Settings()

    assert settings.the_odds_api_key is not None
    assert settings.the_odds_api_key.get_secret_value() == "process-secret"
