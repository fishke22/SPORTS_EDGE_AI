from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from sports_edge_ai.application.checkpoint_backend import (
    CheckpointBackendBusyError,
    CheckpointBackendCapabilities,
    CheckpointBackendConflictError,
    CheckpointBackendQuotaError,
    StoredCheckpoint,
)
from sports_edge_ai.infrastructure.operational_checkpoint import (
    CHECKPOINT_CHUNK_BYTES,
    verify_operational_checkpoint,
)

_POINTER_SCHEMA_VERSION = "local-checkpoint-pointer-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHECKPOINT_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalFilesystemCheckpointBackend:
    """Reference backend for contract tests; never a remote-live backend."""

    def __init__(self, root: Path, *, quota_bytes: int | None = None) -> None:
        self.root = root.expanduser().resolve()
        self.quota_bytes = quota_bytes
        if quota_bytes is not None and quota_bytes < 0:
            raise ValueError("quota_bytes must be non-negative")

    @property
    def capabilities(self) -> CheckpointBackendCapabilities:
        return CheckpointBackendCapabilities(
            backend_id="local-filesystem-reference-v1",
            private_storage=True,
            durable_storage=True,
            automatic_billing_possible=False,
            atomic_publish=True,
            versioned_objects=True,
            single_writer_guard=True,
            quota_fail_closed=True,
            secret_separation=True,
            portable_export=True,
            remote_access=False,
            reference_only=True,
        )

    @property
    def _objects(self) -> Path:
        return self.root / "objects"

    @property
    def _pointer(self) -> Path:
        return self.root / "current.json"

    @property
    def _lock(self) -> Path:
        return self.root / ".publish.lock"

    def _read_pointer(self) -> StoredCheckpoint | None:
        if not self._pointer.is_file():
            return None
        payload = json.loads(self._pointer.read_text(encoding="utf-8"))
        if payload.get("schema_version") != _POINTER_SCHEMA_VERSION:
            raise RuntimeError("checkpoint backend pointer schema is unsupported")
        object_name = str(payload.get("object_name", ""))
        if (
            not object_name
            or "/" in object_name
            or "\\" in object_name
            or object_name in {".", ".."}
        ):
            raise RuntimeError("checkpoint backend pointer object name is invalid")
        generation = str(payload.get("generation", ""))
        sha256 = str(payload.get("sha256", ""))
        size = payload.get("bytes")
        if len(generation) != 64 or len(sha256) != 64:
            raise RuntimeError("checkpoint backend pointer digest is invalid")
        if not isinstance(size, int) or size < 0:
            raise RuntimeError("checkpoint backend pointer size is invalid")
        return StoredCheckpoint(
            backend_id=self.capabilities.backend_id,
            generation=generation,
            sha256=sha256,
            bytes=size,
            object_name=object_name,
        )

    def latest(self) -> StoredCheckpoint | None:
        current = self._read_pointer()
        if current is None:
            return None
        object_path = self._objects / current.object_name
        if not object_path.is_file():
            raise RuntimeError("checkpoint backend current object is missing")
        if object_path.stat().st_size != current.bytes:
            raise RuntimeError("checkpoint backend current object size mismatch")
        if _sha256(object_path) != current.sha256:
            raise RuntimeError("checkpoint backend current object checksum mismatch")
        return current

    def _used_bytes(self) -> int:
        if not self._objects.is_dir():
            return 0
        return sum(path.stat().st_size for path in self._objects.glob("*.zip") if path.is_file())

    def _acquire_lock(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            return os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise CheckpointBackendBusyError(
                "checkpoint backend writer lock is already held"
            ) from exc

    def publish(
        self,
        checkpoint_path: Path,
        *,
        expected_generation: str | None,
    ) -> StoredCheckpoint:
        source = checkpoint_path.expanduser().resolve()
        verification = verify_operational_checkpoint(source)
        source_sha = verification.sha256
        source_bytes = source.stat().st_size
        object_name = f"{source_sha}.zip"
        generation = source_sha

        lock_fd = self._acquire_lock()
        try:
            current = self.latest()
            current_generation = None if current is None else current.generation
            if current_generation != expected_generation:
                raise CheckpointBackendConflictError(
                    "checkpoint backend generation changed; publish rejected"
                )

            object_path = self._objects / object_name
            object_already_present = object_path.is_file()
            additional_bytes = 0 if object_already_present else source_bytes
            if (
                self.quota_bytes is not None
                and self._used_bytes() + additional_bytes > self.quota_bytes
            ):
                raise CheckpointBackendQuotaError(
                    "checkpoint backend free quota would be exceeded; publish rejected"
                )

            self._objects.mkdir(parents=True, exist_ok=True)
            if not object_already_present:
                with NamedTemporaryFile(
                    prefix=".checkpoint-object-",
                    suffix=".tmp",
                    dir=self._objects,
                    delete=False,
                ) as temporary_handle:
                    temporary_object = Path(temporary_handle.name)
                try:
                    shutil.copyfile(source, temporary_object)
                    if temporary_object.stat().st_size != source_bytes:
                        raise RuntimeError("checkpoint backend object copy size mismatch")
                    if _sha256(temporary_object) != source_sha:
                        raise RuntimeError("checkpoint backend object copy checksum mismatch")
                    temporary_object.replace(object_path)
                except Exception:
                    temporary_object.unlink(missing_ok=True)
                    raise
            elif (
                object_path.stat().st_size != source_bytes
                or _sha256(object_path) != source_sha
            ):
                raise RuntimeError("checkpoint backend existing object is corrupt")

            stored = StoredCheckpoint(
                backend_id=self.capabilities.backend_id,
                generation=generation,
                sha256=source_sha,
                bytes=source_bytes,
                object_name=object_name,
            )
            pointer_payload = {
                "schema_version": _POINTER_SCHEMA_VERSION,
                "backend_id": stored.backend_id,
                "generation": stored.generation,
                "sha256": stored.sha256,
                "bytes": stored.bytes,
                "object_name": stored.object_name,
            }
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".current-",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as temporary_handle:
                temporary_pointer = Path(temporary_handle.name)
                json.dump(
                    pointer_payload,
                    temporary_handle,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                temporary_handle.flush()
                os.fsync(temporary_handle.fileno())
            try:
                temporary_pointer.replace(self._pointer)
            except Exception:
                temporary_pointer.unlink(missing_ok=True)
                raise
            return stored
        finally:
            os.close(lock_fd)
            self._lock.unlink(missing_ok=True)

    def fetch_latest(self, destination_dir: Path) -> Path:
        current = self.latest()
        if current is None:
            raise FileNotFoundError("checkpoint backend has no current checkpoint")

        destination_root = destination_dir.expanduser().resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = destination_root / current.object_name
        source = self._objects / current.object_name
        with NamedTemporaryFile(
            prefix=".checkpoint-download-",
            suffix=".tmp",
            dir=destination_root,
            delete=False,
        ) as temporary_handle:
            temporary_download = Path(temporary_handle.name)
        try:
            shutil.copyfile(source, temporary_download)
            if temporary_download.stat().st_size != current.bytes:
                raise RuntimeError("downloaded checkpoint size mismatch")
            if _sha256(temporary_download) != current.sha256:
                raise RuntimeError("downloaded checkpoint checksum mismatch")
            verify_operational_checkpoint(temporary_download)
            temporary_download.replace(destination)
        except Exception:
            temporary_download.unlink(missing_ok=True)
            raise
        return destination
