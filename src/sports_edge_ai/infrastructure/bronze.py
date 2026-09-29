from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sports_edge_ai.common.root import ProjectPaths


@dataclass(frozen=True, slots=True)
class BronzeObject:
    ingest_run_id: str
    provider: str
    payload_sha256: str
    relative_path: str
    manifest_relative_path: str
    observed_at: datetime
    ingested_at: datetime
    object_bytes: int


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def write_bronze_payload(
    *,
    paths: ProjectPaths,
    provider: str,
    payload: bytes,
    observed_at: datetime,
    ingested_at: datetime,
    schema_version: str,
    media_type: str = "application/json",
) -> BronzeObject:
    _require_aware(observed_at, "observed_at")
    _require_aware(ingested_at, "ingested_at")
    if not provider or "/" in provider or "\\" in provider:
        raise ValueError("provider must be a simple identifier")

    observed_utc = observed_at.astimezone(UTC)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    run_material = f"{provider}|{observed_utc.isoformat()}|{payload_sha256}".encode()
    ingest_run_id = hashlib.sha256(run_material).hexdigest()[:32]
    partition = (
        paths.bronze
        / provider
        / f"year={observed_utc:%Y}"
        / f"month={observed_utc:%m}"
        / f"day={observed_utc:%d}"
    )
    object_path = partition / "objects" / f"{payload_sha256}.json"
    manifest_path = partition / "manifests" / f"{ingest_run_id}.json"

    object_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists():
        if object_path.read_bytes() != payload:
            raise RuntimeError("content-addressed Bronze object hash collision")
    else:
        object_path.write_bytes(payload)

    manifest = {
        "ingest_run_id": ingest_run_id,
        "provider": provider,
        "schema_version": schema_version,
        "observed_at": observed_at.isoformat(),
        "ingested_at": ingested_at.isoformat(),
        "payload_sha256": payload_sha256,
        "object_bytes": len(payload),
        "media_type": media_type,
        "public_export_allowed": False,
        "relative_path": _relative(paths.root, object_path),
    }
    encoded_manifest = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if manifest_path.exists():
        if manifest_path.read_text(encoding="utf-8") != encoded_manifest:
            raise RuntimeError("Bronze manifest is immutable and already differs")
    else:
        manifest_path.write_text(encoded_manifest, encoding="utf-8", newline="\n")

    return BronzeObject(
        ingest_run_id=ingest_run_id,
        provider=provider,
        payload_sha256=payload_sha256,
        relative_path=_relative(paths.root, object_path),
        manifest_relative_path=_relative(paths.root, manifest_path),
        observed_at=observed_at,
        ingested_at=ingested_at,
        object_bytes=len(payload),
    )
