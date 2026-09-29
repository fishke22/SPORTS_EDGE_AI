from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_ENV_VAR = "SPORTS_EDGE_ROOT"
ROOT_MARKER = ".sports-edge-root"


class ProjectRootNotFound(RuntimeError):
    """Raised when a trustworthy project root cannot be resolved."""


def _looks_like_root(path: Path) -> bool:
    return (path / ROOT_MARKER).is_file() or (
        (path / "pyproject.toml").is_file() and (path / ".git").exists()
    )


def _walk_up(start: Path) -> Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if _looks_like_root(candidate):
            return candidate
    return None


def resolve_project_root(start: Path | None = None) -> Path:
    override = os.getenv(ROOT_ENV_VAR, "").strip()
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.is_dir():
            raise ProjectRootNotFound(
                f"{ROOT_ENV_VAR} points to a directory that does not exist: {candidate}"
            )
        if not _looks_like_root(candidate):
            raise ProjectRootNotFound(
                f"{ROOT_ENV_VAR} does not point to a SPORTS_EDGE_AI project root: {candidate}"
            )
        return candidate

    for origin in (start or Path.cwd(), Path(__file__)):
        found = _walk_up(Path(origin))
        if found is not None:
            return found

    raise ProjectRootNotFound(
        f"Unable to resolve project root. Set {ROOT_ENV_VAR} or run inside the repository."
    )


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> ProjectPaths:
        return cls(resolve_project_root(start))

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def bronze(self) -> Path:
        return self.data / "bronze"

    @property
    def silver(self) -> Path:
        return self.data / "silver"

    @property
    def gold(self) -> Path:
        return self.data / "gold"

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def database(self) -> Path:
        return self.state / "sports_edge.duckdb"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.bronze,
            self.silver,
            self.gold,
            self.state,
            self.config,
            self.models,
            self.reports,
            self.logs,
            self.backups,
        ):
            path.mkdir(parents=True, exist_ok=True)
