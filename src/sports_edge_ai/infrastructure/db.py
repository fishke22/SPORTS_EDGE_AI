from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from sports_edge_ai.common.root import ProjectPaths

MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class MigrationResult:
    applied: tuple[str, ...]
    current_version: str | None


def connect(paths: ProjectPaths | None = None) -> duckdb.DuckDBPyConnection:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    return duckdb.connect(str(effective_paths.database))


def connect_readonly(paths: ProjectPaths | None = None) -> duckdb.DuckDBPyConnection:
    effective_paths = paths or ProjectPaths.discover()
    if not effective_paths.database.is_file():
        raise FileNotFoundError(effective_paths.database)
    return duckdb.connect(str(effective_paths.database), read_only=True)


def current_schema_version(paths: ProjectPaths | None = None) -> str | None:
    effective_paths = paths or ProjectPaths.discover()
    if not effective_paths.database.is_file():
        return None
    connection = connect_readonly(effective_paths)
    try:
        table_exists = connection.execute(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_name = 'schema_migrations'
            """
        ).fetchone()
        if table_exists is None or table_exists[0] == 0:
            return None
        row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        return None if row is None else row[0]
    finally:
        connection.close()


def _migration_files(root: Path) -> list[Path]:
    migration_dir = root / "sql" / "migrations"
    return sorted(
        path for path in migration_dir.glob("*.sql") if MIGRATION_PATTERN.match(path.name)
    )


def latest_migration_version(paths: ProjectPaths | None = None) -> str | None:
    effective_paths = paths or ProjectPaths.discover()
    migrations = _migration_files(effective_paths.root)
    if not migrations:
        return None
    match = MIGRATION_PATTERN.match(migrations[-1].name)
    return None if match is None else match.group("version")


def migrate(paths: ProjectPaths | None = None) -> MigrationResult:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    connection = connect(effective_paths)
    applied: list[str] = []

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                sha256 VARCHAR NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
            )
            """
        )

        existing = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT version, sha256 FROM schema_migrations ORDER BY version"
            ).fetchall()
        }

        for path in _migration_files(effective_paths.root):
            match = MIGRATION_PATTERN.match(path.name)
            if match is None:
                continue

            version = match.group("version")
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

            if version in existing:
                if existing[version] != checksum:
                    raise RuntimeError(
                        f"Applied migration {version} checksum differs from {path.name}"
                    )
                continue

            connection.execute("BEGIN")
            try:
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, sha256) VALUES (?, ?, ?)",
                    [version, path.name, checksum],
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            applied.append(version)

        current_row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        current_version = None if current_row is None else current_row[0]
        return MigrationResult(tuple(applied), current_version)
    finally:
        connection.close()
