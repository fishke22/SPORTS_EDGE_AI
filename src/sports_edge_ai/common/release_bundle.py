from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sports_edge_ai.common.publication_audit import run_audit
from sports_edge_ai.common.root import ProjectPaths

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class ReleaseBundle:
    relative_path: str
    sha256: str
    manifest_sha256: str
    file_count: int
    version: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_tracked(root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(sorted(line.strip() for line in result.stdout.splitlines() if line.strip()))


def _project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        payload = tomllib.load(handle)
    return str(payload["project"]["version"])


def build_release_bundle(
    *,
    paths: ProjectPaths | None = None,
    output_dir: Path | None = None,
    enforce_publication_audit: bool = True,
) -> ReleaseBundle:
    effective_paths = paths or ProjectPaths.discover()
    root = effective_paths.root
    if enforce_publication_audit:
        audit = run_audit(root)
        if audit["blocker_count"] != 0 or audit["warning_count"] != 0:
            raise RuntimeError("publication audit must have zero blockers and zero warnings")

    frontend_dist = root / "frontend" / "dist"
    if not (frontend_dist / "index.html").is_file():
        raise RuntimeError(
            "frontend production build is missing; run npm --prefix frontend run build"
        )

    files: dict[str, bytes] = {}
    for relative in _git_tracked(root):
        path = root / relative
        if not path.is_file():
            continue
        files[relative.replace("\\", "/")] = path.read_bytes()
    for path in sorted(frontend_dist.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            files[relative] = path.read_bytes()

    manifest_files = [
        {
            "relative_path": relative,
            "sha256": _sha256_bytes(data),
            "bytes": len(data),
        }
        for relative, data in sorted(files.items())
    ]
    version = _project_version(root)
    manifest = {
        "schema_version": "sports-edge-release-v1",
        "project": "sports-edge-ai",
        "version": version,
        "includes_runtime_state": False,
        "includes_provider_raw_data": False,
        "files": manifest_files,
    }
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_sha256 = _sha256_bytes(manifest_bytes)

    target_dir = (output_dir or (effective_paths.backups / "releases")).resolve()
    try:
        target_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("release output_dir must stay under PROJECT_ROOT") from exc
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"sports-edge-ai-{version}-{manifest_sha256[:12]}.zip"
    temporary = target.with_suffix(".zip.tmp")
    if temporary.exists():
        temporary.unlink()

    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative, data in sorted(files.items()):
            info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
        manifest_info = zipfile.ZipInfo("release-manifest.json", ZIP_TIMESTAMP)
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        manifest_info.external_attr = 0o100644 << 16
        archive.writestr(manifest_info, manifest_bytes)

    temporary.replace(target)
    archive_bytes = target.read_bytes()
    return ReleaseBundle(
        relative_path=target.relative_to(root).as_posix(),
        sha256=_sha256_bytes(archive_bytes),
        manifest_sha256=manifest_sha256,
        file_count=len(files),
        version=version,
    )
