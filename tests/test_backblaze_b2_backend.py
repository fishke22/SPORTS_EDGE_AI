from __future__ import annotations

import base64
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

from sports_edge_ai.application.backblaze_b2_status import (
    get_backblaze_b2_preflight_status,
)
from sports_edge_ai.application.checkpoint_backend import (
    CheckpointBackendConflictError,
    CheckpointBackendQuotaError,
)
from sports_edge_ai.common.root import ProjectPaths
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.infrastructure.db import migrate
from sports_edge_ai.infrastructure.operational_checkpoint import (
    create_operational_checkpoint,
    verify_operational_checkpoint,
)
from sports_edge_ai.infrastructure.providers.backblaze_b2 import (
    B2HttpResponse,
    BackblazeB2ApiError,
    BackblazeB2CheckpointBackend,
)

PROJECT_ROOT = Path(__file__).parents[1]


def _portable_root(tmp_path: Path, name: str) -> ProjectPaths:
    root = tmp_path / name
    migrations = root / "sql" / "migrations"
    migrations.mkdir(parents=True)
    (root / ".sports-edge-root").write_text("SPORTS_EDGE_AI\n", encoding="utf-8")
    for migration in (PROJECT_ROOT / "sql" / "migrations").glob("*.sql"):
        shutil.copy2(migration, migrations / migration.name)
    return ProjectPaths(root)


def _checkpoint(paths: ProjectPaths, marker: str, created_at: datetime) -> Path:
    if not paths.database.exists():
        migrate(paths)
    paths.ensure_runtime_dirs()
    (paths.bronze / "b2-marker.txt").write_text(marker, encoding="utf-8")
    artifact = create_operational_checkpoint(paths=paths, created_at=created_at)
    return paths.root / artifact.relative_path


def _settings(
    tmp_path: Path,
    *,
    no_payment: bool = True,
    storage_cap: bool = True,
    download_cap: bool = True,
    transaction_caps: bool = True,
) -> Settings:
    return Settings(
        project_root=tmp_path,
        backblaze_b2_key_id="data-id",
        backblaze_b2_application_key="data-secret",
        backblaze_b2_pointer_key_id="pointer-id",
        backblaze_b2_pointer_application_key="pointer-secret",
        backblaze_b2_bucket_id="bucket-1",
        backblaze_b2_bucket_name="sports-edge-test",
        backblaze_b2_name_prefix="sports-edge-ai/",
        backblaze_b2_no_payment_method_confirmed=no_payment,
        backblaze_b2_zero_dollar_storage_cap_confirmed=storage_cap,
        backblaze_b2_zero_dollar_download_cap_confirmed=download_cap,
        backblaze_b2_transaction_caps_confirmed=transaction_caps,
    )


class ScenarioB2Transport:
    def __init__(self) -> None:
        self.bucket_type = "allPrivate"
        self.lifecycle_rules: list[dict[str, object]] = []
        self.replication_enabled = False
        self.revision = 7
        self.bucket_info: dict[str, str] = {}
        self.stored_body: bytes | None = None
        self.stored_name: str | None = None
        self.stored_file_id = "file-1"
        self.quota_on_upload = False
        self.authorize_error = False
        self.update_conflict = False
        self.data_prefix: str | None = "sports-edge-ai/"
        self.data_capabilities = [
            "listBuckets",
            "readFiles",
            "writeFiles",
            "readBucketReplications",
        ]

    def _json(self, status: int, payload: dict[str, object]) -> B2HttpResponse:
        return B2HttpResponse(
            status=status,
            body=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    def _key_id(self, authorization: str) -> str:
        encoded = authorization.removeprefix("Basic ")
        decoded = base64.b64decode(encoded).decode("utf-8")
        return decoded.split(":", 1)[0]

    def _bucket_payload(self) -> dict[str, object]:
        replication_value: dict[str, object] = {
            "asReplicationDestination": None,
            "asReplicationSource": None,
        }
        if self.replication_enabled:
            replication_value["asReplicationSource"] = {
                "replicationRules": [
                    {
                        "destinationBucketId": "other",
                        "isEnabled": True,
                        "replicationRuleName": "enabled-rule",
                    }
                ]
            }
        return {
            "accountId": "account-1",
            "bucketId": "bucket-1",
            "bucketName": "sports-edge-test",
            "bucketType": self.bucket_type,
            "bucketInfo": dict(self.bucket_info),
            "lifecycleRules": list(self.lifecycle_rules),
            "replicationConfiguration": {
                "isClientAuthorizedToRead": True,
                "value": replication_value,
            },
            "revision": self.revision,
        }

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> B2HttpResponse:
        assert timeout_seconds > 0
        if url.endswith("/b2_authorize_account"):
            if self.authorize_error:
                return self._json(
                    401,
                    {
                        "status": 401,
                        "code": "unauthorized",
                        "message": "data-secret pointer-secret must never escape",
                    },
                )
            key_id = self._key_id(headers["Authorization"])
            if key_id == "data-id":
                allowed = {
                    "buckets": [{"id": "bucket-1", "name": "sports-edge-test"}],
                    "capabilities": list(self.data_capabilities),
                    "namePrefix": self.data_prefix,
                }
                token = "data-token"
            elif key_id == "pointer-id":
                allowed = {
                    "buckets": [],
                    "capabilities": ["listBuckets", "writeBuckets"],
                    "namePrefix": None,
                }
                token = "pointer-token"
            else:
                raise AssertionError(f"unexpected key id: {key_id}")
            return self._json(
                200,
                {
                    "accountId": "account-1",
                    "authorizationToken": token,
                    "apiInfo": {
                        "storageApi": {
                            "apiUrl": "https://api.example",
                            "downloadUrl": "https://download.example",
                            "allowed": allowed,
                        }
                    },
                },
            )

        if url.endswith("/b2_list_buckets"):
            assert method == "POST"
            return self._json(200, {"buckets": [self._bucket_payload()]})

        if "/b2_get_upload_url?" in url:
            return self._json(
                200,
                {
                    "bucketId": "bucket-1",
                    "uploadUrl": "https://upload.example/file",
                    "authorizationToken": "upload-token",
                },
            )

        if url == "https://upload.example/file":
            if self.quota_on_upload:
                return self._json(
                    403,
                    {
                        "status": 403,
                        "code": "storage_cap_exceeded",
                        "message": "hard cap",
                    },
                )
            assert body is not None
            self.stored_body = body
            self.stored_name = unquote(headers["X-Bz-File-Name"])
            return self._json(
                200,
                {
                    "fileId": self.stored_file_id,
                    "fileName": self.stored_name,
                    "contentSha1": hashlib.sha1(body, usedforsecurity=False).hexdigest(),
                    "contentLength": len(body),
                },
            )

        if url.endswith("/b2_update_bucket"):
            assert body is not None
            payload = json.loads(body.decode("utf-8"))
            if self.update_conflict or payload["ifRevisionIs"] != self.revision:
                return self._json(
                    409,
                    {"status": 409, "code": "conflict", "message": "revision changed"},
                )
            self.bucket_info = dict(payload["bucketInfo"])
            self.revision += 1
            return self._json(200, self._bucket_payload())

        if "/b2_download_file_by_id?" in url:
            if self.stored_body is None:
                raise AssertionError("download requested before upload")
            return B2HttpResponse(
                status=200,
                body=self.stored_body,
                headers={
                    "x-bz-content-sha1": hashlib.sha1(
                        self.stored_body,
                        usedforsecurity=False,
                    ).hexdigest()
                },
            )

        raise AssertionError(f"unexpected request: {method} {url}")


def test_preflight_remains_blocked_without_payment_method_evidence(tmp_path: Path) -> None:
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path, no_payment=False),
        transport=ScenarioB2Transport(),
    )

    assessment = backend.preflight(provider_round_trip_verified=True)

    assert assessment.remote_live_ready is False
    assert assessment.storage_operations_allowed is False
    assert "NO_PAYMENT_METHOD_NOT_CONFIRMED" in assessment.blockers
    assert "AUTOMATIC_BILLING_POSSIBLE" in assessment.blockers


def test_preflight_can_only_be_ready_after_all_manual_and_provider_evidence(
    tmp_path: Path,
) -> None:
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path),
        transport=ScenarioB2Transport(),
    )

    before_round_trip = backend.preflight(provider_round_trip_verified=False)
    after_round_trip = backend.preflight(provider_round_trip_verified=True)

    assert before_round_trip.storage_operations_allowed is True
    assert before_round_trip.remote_live_ready is False
    assert before_round_trip.blockers == ("B2_PROVIDER_ROUND_TRIP_NOT_VERIFIED",)
    assert after_round_trip.remote_live_ready is True
    assert after_round_trip.blockers == ()


def test_preflight_rejects_public_bucket_replication_and_overprivileged_key(
    tmp_path: Path,
) -> None:
    transport = ScenarioB2Transport()
    transport.bucket_type = "allPublic"
    transport.replication_enabled = True
    transport.data_prefix = None
    transport.data_capabilities.append("deleteFiles")
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path),
        transport=transport,
    )

    assessment = backend.preflight(provider_round_trip_verified=True)

    assert assessment.remote_live_ready is False
    assert "B2_BUCKET_NOT_PRIVATE" in assessment.blockers
    assert "B2_CLOUD_REPLICATION_ENABLED_OR_UNVERIFIED" in assessment.blockers
    assert "B2_DATA_KEY_NOT_PREFIX_SCOPED" in assessment.blockers
    assert "B2_DATA_KEY_CAPABILITIES_NOT_MINIMAL" in assessment.blockers


def test_b2_backend_round_trip_and_stale_generation_rejection(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path, "source")
    first_archive = _checkpoint(
        paths,
        "first",
        datetime(2026, 9, 30, 13, 0, tzinfo=UTC),
    )
    transport = ScenarioB2Transport()
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path),
        transport=transport,
    )

    stored = backend.publish(first_archive, expected_generation=None)
    current = backend.latest()
    downloaded = backend.fetch_latest(tmp_path / "downloads")

    assert stored.generation == "8"
    assert current == stored
    assert verify_operational_checkpoint(downloaded).sha256 == stored.sha256
    assert transport.stored_name == stored.object_name

    second_archive = _checkpoint(
        paths,
        "second",
        datetime(2026, 9, 30, 13, 1, tzinfo=UTC),
    )
    with pytest.raises(CheckpointBackendConflictError, match="generation changed"):
        backend.publish(second_archive, expected_generation="7")

    assert backend.latest() == stored


def test_b2_backend_403_cap_fails_before_pointer_update(tmp_path: Path) -> None:
    paths = _portable_root(tmp_path, "source")
    archive = _checkpoint(
        paths,
        "quota",
        datetime(2026, 9, 30, 13, 0, tzinfo=UTC),
    )
    transport = ScenarioB2Transport()
    transport.quota_on_upload = True
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path),
        transport=transport,
    )

    with pytest.raises(CheckpointBackendQuotaError, match="zero-cost cap"):
        backend.publish(archive, expected_generation=None)

    assert transport.bucket_info == {}
    assert transport.revision == 7


def test_b2_backend_409_cas_conflict_keeps_current_pointer_unchanged(
    tmp_path: Path,
) -> None:
    paths = _portable_root(tmp_path, "source")
    archive = _checkpoint(
        paths,
        "conflict",
        datetime(2026, 9, 30, 13, 0, tzinfo=UTC),
    )
    transport = ScenarioB2Transport()
    transport.update_conflict = True
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path),
        transport=transport,
    )

    with pytest.raises(CheckpointBackendConflictError, match="revision changed"):
        backend.publish(archive, expected_generation=None)

    assert transport.bucket_info == {}
    assert transport.revision == 7


def test_b2_errors_never_echo_application_keys(tmp_path: Path) -> None:
    transport = ScenarioB2Transport()
    transport.authorize_error = True
    backend = BackblazeB2CheckpointBackend(
        settings=_settings(tmp_path),
        transport=transport,
    )

    with pytest.raises(BackblazeB2ApiError) as exc_info:
        backend.preflight()

    message = str(exc_info.value)
    assert "data-secret" not in message
    assert "pointer-secret" not in message
    assert "unauthorized" in message


def test_offline_status_does_not_contact_provider_and_stays_fail_closed(
    tmp_path: Path,
) -> None:
    settings = Settings(
        project_root=tmp_path,
        backblaze_b2_zero_dollar_storage_cap_confirmed=True,
        backblaze_b2_zero_dollar_download_cap_confirmed=True,
        backblaze_b2_transaction_caps_confirmed=True,
    )

    assessment = get_backblaze_b2_preflight_status(settings=settings, live=False)

    assert assessment.remote_live_ready is False
    assert "NO_PAYMENT_METHOD_NOT_CONFIRMED" in assessment.blockers
    assert "B2_CREDENTIALS_NOT_CONFIGURED" in assessment.blockers
    assert "B2_PROVIDER_ROUND_TRIP_NOT_VERIFIED" in assessment.blockers
