from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import IO, TypedDict

from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.infrastructure.db import (
    connect,
    current_schema_version,
    latest_migration_version,
    migrate,
)

OPERATIONAL_CHECKPOINT_SCHEMA_VERSION = "sports-edge-operational-checkpoint-v1"
OPERATIONAL_CHECKPOINT_ROOTS = (
    "data/bronze",
    "data/silver",
    "data/gold",
    "state",
    "models",
    "reports",
)
CHECKPOINT_CHUNK_BYTES = 1024 * 1024


class CheckpointFileRow(TypedDict):
    relative_path: str
    sha256: str
    bytes: int


@dataclass(frozen=True, slots=True)
class OperationalCheckpointArtifact:
    relative_path: str
    sha256: str
    manifest_sha256: str
    file_count: int
    total_bytes: int
    source_schema_version: str


@dataclass(frozen=True, slots=True)
class OperationalCheckpointVerification:
    source_name: str
    sha256: str
    manifest_sha256: str
    created_at: datetime
    file_count: int
    total_bytes: int
    source_schema_version: str
    includes_raw_data: bool
    public_export_allowed: bool
    secret_transport: bool


@dataclass(frozen=True, slots=True)
class OperationalCheckpointRestoreResult:
    source_checkpoint: str
    restored_files: tuple[str, ...]
    source_schema_version: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHECKPOINT_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_stream(handle: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for chunk in iter(lambda: handle.read(CHECKPOINT_CHUNK_BYTES), b""):
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total


def _allowed_relative_path(relative: str) -> bool:
    pure = PurePosixPath(relative)
    if (
        not pure.parts
        or pure.is_absolute()
        or ".." in pure.parts
        or "\\" in relative
        or ":" in relative
        or any(ord(character) < 32 for character in relative)
        or pure.as_posix() != relative
    ):
        return False
    parts = pure.parts
    return any(
        parts[: len(PurePosixPath(root).parts)] == PurePosixPath(root).parts
        for root in OPERATIONAL_CHECKPOINT_ROOTS
    )


def _iter_checkpoint_files(paths: ProjectPaths) -> tuple[Path, ...]:
    files: list[Path] = []
    for root_name in OPERATIONAL_CHECKPOINT_ROOTS:
        root = paths.root / PurePosixPath(root_name)
        if not root.is_dir():
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        )
    return tuple(sorted(files, key=lambda path: path.relative_to(paths.root).as_posix()))

def _configured_secret_tokens(paths: ProjectPaths) -> tuple[bytes, ...]:
    settings = Settings(project_root=paths.root)
    if settings.the_odds_api_key is None:
        return ()
    value = settings.the_odds_api_key.get_secret_value().strip()
    return () if not value else (value.encode("utf-8"),)


def _assert_no_configured_secret_leakage(paths: ProjectPaths, files: tuple[Path, ...]) -> None:
    tokens = _configured_secret_tokens(paths)
    if not tokens:
        return
    carry_size = max(len(token) for token in tokens) - 1
    for path in files:
        carry = b""
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHECKPOINT_CHUNK_BYTES), b""):
                window = carry + chunk
                if any(token in window for token in tokens):
                    relative = path.relative_to(paths.root).as_posix()
                    raise RuntimeError(
                        "configured credential leaked into operational checkpoint source: "
                        f"{relative}"
                    )
                carry = window[-carry_size:] if carry_size > 0 else b""



def _checkpoint_database(paths: ProjectPaths) -> str:
    current = current_schema_version(paths)
    latest = latest_migration_version(paths)
    if current is None:
        raise RuntimeError("operational checkpoint requires an initialized DuckDB state")
    if latest is None:
        raise RuntimeError("operational checkpoint requires tracked SQL migrations")
    if current != latest:
        raise RuntimeError(
            "operational checkpoint requires current schema to equal latest migration: "
            f"current={current}, latest={latest}"
        )

    connection = connect(paths)
    try:
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return current


def create_operational_checkpoint(
    *,
    paths: ProjectPaths | None = None,
    created_at: datetime | None = None,
) -> OperationalCheckpointArtifact:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")

    schema_version = _checkpoint_database(effective_paths)
    files = _iter_checkpoint_files(effective_paths)
    _assert_no_configured_secret_leakage(effective_paths, files)
    rows: list[CheckpointFileRow] = [
        {
            "relative_path": path.relative_to(effective_paths.root).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    total_bytes = sum(row["bytes"] for row in rows)
    manifest = {
        "schema_version": OPERATIONAL_CHECKPOINT_SCHEMA_VERSION,
        "created_at": timestamp.astimezone(UTC).isoformat(),
        "source_schema_version": schema_version,
        "includes_raw_data": True,
        "public_export_allowed": False,
        "secret_transport": False,
        "allowed_roots": list(OPERATIONAL_CHECKPOINT_ROOTS),
        "file_count": len(rows),
        "total_bytes": total_bytes,
        "files": rows,
    }
    manifest_bytes = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()

    checkpoint_dir = effective_paths.backups / "operational-checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    archive_name = (
        f"operational-checkpoint-{timestamp.astimezone(UTC):%Y%m%dT%H%M%S%fZ}-"
        f"{manifest_hash[:12]}.zip"
    )
    archive_path = checkpoint_dir / archive_name
    if archive_path.exists():
        raise FileExistsError(archive_path)

    with NamedTemporaryFile(
        prefix=".operational-checkpoint-",
        suffix=".tmp",
        dir=checkpoint_dir,
        delete=False,
    ) as temporary_handle:
        temporary_archive = Path(temporary_handle.name)
    try:
        with zipfile.ZipFile(
            temporary_archive,
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
        if archive_path.exists():
            raise FileExistsError(archive_path)
        temporary_archive.replace(archive_path)
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise

    return OperationalCheckpointArtifact(
        relative_path=archive_path.relative_to(effective_paths.root).as_posix(),
        sha256=_sha256(archive_path),
        manifest_sha256=manifest_hash,
        file_count=len(rows),
        total_bytes=total_bytes,
        source_schema_version=schema_version,
    )


def _validated_manifest(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, object], tuple[CheckpointFileRow, ...], bytes, int]:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("operational checkpoint contains duplicate archive entries")
    try:
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except KeyError as exc:
        raise ValueError("operational checkpoint manifest.json is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("operational checkpoint manifest.json is invalid JSON") from exc

    if not isinstance(manifest, dict):
        raise ValueError("operational checkpoint manifest must be an object")
    if manifest.get("schema_version") != OPERATIONAL_CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unsupported operational checkpoint schema version")
    if manifest.get("includes_raw_data") is not True:
        raise ValueError("operational checkpoint raw-data contract is invalid")
    if manifest.get("public_export_allowed") is not False:
        raise ValueError("operational checkpoint must remain private")
    if manifest.get("secret_transport") is not False:
        raise ValueError("operational checkpoint cannot be a secret transport")
    if manifest.get("allowed_roots") != list(OPERATIONAL_CHECKPOINT_ROOTS):
        raise ValueError("operational checkpoint allowed roots do not match this runtime")

    source_schema = str(manifest.get("source_schema_version", ""))
    if len(source_schema) != 4 or not source_schema.isdigit():
        raise ValueError("operational checkpoint source schema version is invalid")

    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("operational checkpoint files must be a list")
    if manifest.get("file_count") != len(rows):
        raise ValueError("operational checkpoint file_count does not match files")

    validated: list[CheckpointFileRow] = []
    declared_names: set[str] = {"manifest.json"}
    calculated_total = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid operational checkpoint file entry")
        relative = str(row.get("relative_path", ""))
        if not _allowed_relative_path(relative):
            raise ValueError(f"operational checkpoint contains disallowed path: {relative}")
        expected_hash = str(row.get("sha256", ""))
        if len(expected_hash) != 64:
            raise ValueError("operational checkpoint file checksum is invalid")
        expected_bytes = row.get("bytes")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ValueError("operational checkpoint file size is invalid")
        if relative in declared_names:
            raise ValueError("operational checkpoint manifest contains duplicate file paths")
        declared_names.add(relative)
        calculated_total += expected_bytes
        validated.append(
            {
                "relative_path": relative,
                "sha256": expected_hash,
                "bytes": expected_bytes,
            }
        )

    if manifest.get("total_bytes") != calculated_total:
        raise ValueError("operational checkpoint total_bytes does not match files")
    if set(names) != declared_names:
        raise ValueError("operational checkpoint contains undeclared archive entries")
    return manifest, tuple(validated), manifest_bytes, calculated_total


def verify_operational_checkpoint(
    checkpoint_path: Path,
) -> OperationalCheckpointVerification:
    source = checkpoint_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    with zipfile.ZipFile(source, mode="r") as archive:
        manifest, rows, manifest_bytes, total_bytes = _validated_manifest(archive)
        for row in rows:
            relative = str(row["relative_path"])
            expected_hash = str(row["sha256"])
            expected_bytes = row["bytes"]
            with archive.open(relative, mode="r") as handle:
                actual_hash, actual_bytes = _hash_stream(handle)
            if actual_hash != expected_hash:
                raise RuntimeError(f"operational checkpoint checksum mismatch: {relative}")
            if actual_bytes != expected_bytes:
                raise RuntimeError(f"operational checkpoint size mismatch: {relative}")

    created_at = datetime.fromisoformat(str(manifest["created_at"]))
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("operational checkpoint created_at must be timezone-aware")

    return OperationalCheckpointVerification(
        source_name=source.name,
        sha256=_sha256(source),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        created_at=created_at,
        file_count=len(rows),
        total_bytes=total_bytes,
        source_schema_version=str(manifest["source_schema_version"]),
        includes_raw_data=True,
        public_export_allowed=False,
        secret_transport=False,
    )


def _existing_operational_files(paths: ProjectPaths) -> tuple[str, ...]:
    existing: list[str] = []
    for root_name in OPERATIONAL_CHECKPOINT_ROOTS:
        root = paths.root / PurePosixPath(root_name)
        if not root.is_dir():
            continue
        existing.extend(
            path.relative_to(paths.root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        )
    return tuple(sorted(existing))


def restore_operational_checkpoint(
    checkpoint_path: Path,
    *,
    paths: ProjectPaths | None = None,
) -> OperationalCheckpointRestoreResult:
    effective_paths = paths or ProjectPaths.discover()
    effective_paths.ensure_runtime_dirs()
    existing = _existing_operational_files(effective_paths)
    if existing:
        raise RuntimeError(
            "operational checkpoint restore requires an empty runtime target; "
            f"found {len(existing)} existing file(s)"
        )

    source = checkpoint_path.expanduser().resolve()
    verification = verify_operational_checkpoint(source)
    latest = latest_migration_version(effective_paths)
    if latest is None:
        raise RuntimeError("operational checkpoint restore requires tracked SQL migrations")
    if verification.source_schema_version != latest:
        raise RuntimeError(
            "operational checkpoint schema does not match checkout migrations: "
            f"checkpoint={verification.source_schema_version}, checkout={latest}"
        )

    with zipfile.ZipFile(source, mode="r") as archive:
        _, rows, _, _ = _validated_manifest(archive)
        with TemporaryDirectory(prefix="sports-edge-restore-") as temporary:
            temp_root = Path(temporary)
            verified: list[tuple[Path, Path, str]] = []
            for row in rows:
                relative = str(row["relative_path"])
                expected_hash = str(row["sha256"])
                expected_bytes = row["bytes"]
                temp_path = temp_root / PurePosixPath(relative)
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                with (
                    archive.open(relative, mode="r") as input_handle,
                    temp_path.open("wb") as output,
                ):
                    for chunk in iter(
                        lambda: input_handle.read(CHECKPOINT_CHUNK_BYTES),
                        b"",
                    ):
                        output.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                if digest.hexdigest() != expected_hash or written != expected_bytes:
                    raise RuntimeError(f"operational checkpoint verification failed: {relative}")
                target = effective_paths.root / PurePosixPath(relative)
                verified.append((temp_path, target, relative))

            restored: list[str] = []
            restored_targets: list[Path] = []
            try:
                for temp_path, target, relative in verified:
                    if target.exists():
                        raise RuntimeError(
                            "operational checkpoint restore target changed during restore: "
                            f"{relative}"
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(temp_path, target)
                    restored.append(relative)
                    restored_targets.append(target)

                migration_result = migrate(effective_paths)
                if migration_result.applied:
                    raise RuntimeError(
                        "restored checkpoint unexpectedly required migrations: "
                        f"{migration_result.applied!r}"
                    )
                if migration_result.current_version != verification.source_schema_version:
                    raise RuntimeError(
                        "restored DuckDB schema does not match checkpoint manifest"
                    )
            except Exception:
                for target in reversed(restored_targets):
                    target.unlink(missing_ok=True)
                raise

    return OperationalCheckpointRestoreResult(
        source_checkpoint=source.name,
        restored_files=tuple(restored),
        source_schema_version=verification.source_schema_version,
    )
