from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ZERO_COST_BACKEND_CONTRACT_VERSION = "zero-cost-checkpoint-backend-v1"


class CheckpointBackendError(RuntimeError):
    """Base error for private operational checkpoint storage."""


class CheckpointBackendConflictError(CheckpointBackendError):
    """Raised when compare-and-swap generation does not match."""


class CheckpointBackendBusyError(CheckpointBackendError):
    """Raised when another writer holds the backend publish lock."""


class CheckpointBackendQuotaError(CheckpointBackendError):
    """Raised before mutation when the configured free quota would be exceeded."""


@dataclass(frozen=True, slots=True)
class CheckpointBackendCapabilities:
    backend_id: str
    private_storage: bool
    durable_storage: bool
    automatic_billing_possible: bool
    atomic_publish: bool
    versioned_objects: bool
    single_writer_guard: bool
    quota_fail_closed: bool
    secret_separation: bool
    portable_export: bool
    remote_access: bool
    reference_only: bool = False


@dataclass(frozen=True, slots=True)
class CheckpointBackendAssessment:
    contract_version: str
    backend_id: str
    remote_live_eligible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoredCheckpoint:
    backend_id: str
    generation: str
    sha256: str
    bytes: int
    object_name: str


class CheckpointBackend(Protocol):
    @property
    def capabilities(self) -> CheckpointBackendCapabilities: ...

    def latest(self) -> StoredCheckpoint | None: ...

    def publish(
        self,
        checkpoint_path: Path,
        *,
        expected_generation: str | None,
    ) -> StoredCheckpoint: ...

    def fetch_latest(self, destination_dir: Path) -> Path: ...


def assess_zero_cost_backend(
    capabilities: CheckpointBackendCapabilities,
) -> CheckpointBackendAssessment:
    blockers: list[str] = []
    if not capabilities.private_storage:
        blockers.append("BACKEND_NOT_PRIVATE")
    if not capabilities.durable_storage:
        blockers.append("BACKEND_NOT_DURABLE")
    if capabilities.automatic_billing_possible:
        blockers.append("AUTOMATIC_BILLING_POSSIBLE")
    if not (capabilities.atomic_publish or capabilities.versioned_objects):
        blockers.append("NO_ATOMIC_OR_VERSIONED_PUBLISH")
    if not capabilities.single_writer_guard:
        blockers.append("NO_SINGLE_WRITER_GUARD")
    if not capabilities.quota_fail_closed:
        blockers.append("NO_QUOTA_FAIL_CLOSED")
    if not capabilities.secret_separation:
        blockers.append("NO_SECRET_SEPARATION")
    if not capabilities.portable_export:
        blockers.append("NO_PORTABLE_EXPORT")
    if not capabilities.remote_access:
        blockers.append("NO_REMOTE_ACCESS")
    if capabilities.reference_only:
        blockers.append("REFERENCE_ONLY_BACKEND")

    return CheckpointBackendAssessment(
        contract_version=ZERO_COST_BACKEND_CONTRACT_VERSION,
        backend_id=capabilities.backend_id,
        remote_live_eligible=not blockers,
        blockers=tuple(blockers),
    )
