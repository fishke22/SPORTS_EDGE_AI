from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.infrastructure.db import connect

BACKUP_SCHEMA_VERSION = "sports-edge-backup-v1"
ALLOWED_BACKUP_ROOTS = ("state", "models", "reports", "config")


@dataclass(frozen=True, slots=True)
class BackupArtifact:
    relative_path: str
    sha256: str
    file_count: int


@dataclass(frozen=True, slots=True)
class RestoreResult:
    restored_files: tuple[str, ...]
    source_backup: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_backup_files(paths: ProjectPaths) -> tuple[Path, ...]:
    files: list[Path] = []
    for root_name in ALLOWED_BACKUP_ROOTS:
        root = paths.root / root_name
        if not root.is_dir():
            continue
        files.extend(path for path in root.rglob("*") if path.is_file() and path.name != ".gitkeep")
    return tuple(sorted(files))


def create_research_backup(
    *,
    paths: ProjectPaths | None = None,
    created_at: datetime | None = None,
) -> BackupArtifact:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")

    if effective_paths.database.is_file():
        connection = connect(effective_paths)
        try:
            connection.execute("CHECKPOINT")
        finally:
            connection.close()

    files = _iter_backup_files(effective_paths)
    manifest_files = [
        {
            "relative_path": path.relative_to(effective_paths.root).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": timestamp.astimezone(UTC).isoformat(),
        "includes_raw_data": False,
        "allowed_roots": list(ALLOWED_BACKUP_ROOTS),
        "files": manifest_files,
    }
    manifest_bytes = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    archive_hash = hashlib.sha256(manifest_bytes).hexdigest()
    archive_name = (
        f"research-backup-{timestamp.astimezone(UTC):%Y%m%dT%H%M%SZ}-{archive_hash[:12]}.zip"
    )
    archive_path = effective_paths.backups / archive_name
    if archive_path.exists():
        raise FileExistsError(archive_path)

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        for path in files:
            archive.write(
                path,
                arcname=path.relative_to(effective_paths.root).as_posix(),
            )

    return BackupArtifact(
        relative_path=archive_path.relative_to(effective_paths.root).as_posix(),
        sha256=_sha256(archive_path),
        file_count=len(files),
    )


def _validated_manifest(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except KeyError as exc:
        raise ValueError("backup manifest.json is missing") from exc
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise ValueError("unsupported backup schema version")
    if manifest.get("includes_raw_data") is not False:
        raise ValueError("backup raw-data policy is not supported")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("backup manifest files must be a list")

    validated: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid backup manifest file entry")
        relative = str(row.get("relative_path", ""))
        pure = PurePosixPath(relative)
        if (
            not pure.parts
            or pure.is_absolute()
            or ".." in pure.parts
            or pure.parts[0] not in ALLOWED_BACKUP_ROOTS
        ):
            raise ValueError("backup contains a disallowed relative path")
        expected_hash = str(row.get("sha256", ""))
        if len(expected_hash) != 64:
            raise ValueError("backup file checksum is invalid")
        validated.append(row)
    return manifest, tuple(validated)


def restore_research_backup(
    backup_path: Path,
    *,
    paths: ProjectPaths | None = None,
    force: bool = False,
) -> RestoreResult:
    if not force:
        raise ValueError("restore requires force=True because it can overwrite local state")
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    source = backup_path.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    with zipfile.ZipFile(source, mode="r") as archive:
        _, rows = _validated_manifest(archive)
        with TemporaryDirectory(dir=effective_paths.backups) as temporary:
            temp_root = Path(temporary)
            verified: list[tuple[Path, Path, str]] = []
            for row in rows:
                relative = str(row["relative_path"])
                expected_hash = str(row["sha256"])
                data = archive.read(relative)
                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash != expected_hash:
                    raise RuntimeError(f"backup checksum mismatch: {relative}")
                temp_path = temp_root / PurePosixPath(relative)
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_bytes(data)
                target = effective_paths.root / PurePosixPath(relative)
                verified.append((temp_path, target, relative))

            restored: list[str] = []
            for temp_path, target, relative in verified:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(temp_path.read_bytes())
                restored.append(relative)

    return RestoreResult(
        restored_files=tuple(restored),
        source_backup=source.name,
    )
