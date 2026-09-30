from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from sports_edge_ai.application.backblaze_b2_preflight import (
    BackblazeB2ManualEvidence,
    BackblazeB2PreflightAssessment,
    BackblazeB2ProviderEvidence,
    assess_backblaze_b2_preflight,
)
from sports_edge_ai.application.checkpoint_backend import (
    CheckpointBackendCapabilities,
    CheckpointBackendConflictError,
    CheckpointBackendError,
    CheckpointBackendQuotaError,
    StoredCheckpoint,
)
from sports_edge_ai.common.settings import Settings
from sports_edge_ai.infrastructure.operational_checkpoint import (
    CHECKPOINT_CHUNK_BYTES,
    verify_operational_checkpoint,
)

B2_AUTHORIZE_URL = "https://api.backblazeb2.com/b2api/v4/b2_authorize_account"
B2_POINTER_INFO_KEY = "sportsEdgeCurrentCheckpointV1"
B2_BACKEND_ID = "backblaze-b2-native-v1"
B2_DEFAULT_MAX_CHECKPOINT_BYTES = 250_000_000

_DATA_REQUIRED_CAPABILITIES = frozenset(
    {"listBuckets", "readFiles", "writeFiles", "readBucketReplications"}
)
_DATA_ALLOWED_CAPABILITIES = _DATA_REQUIRED_CAPABILITIES | frozenset({"listFiles"})
_POINTER_REQUIRED_CAPABILITIES = frozenset({"listBuckets", "writeBuckets"})
_POINTER_ALLOWED_CAPABILITIES = _POINTER_REQUIRED_CAPABILITIES


@dataclass(frozen=True, slots=True)
class B2HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]


class B2Transport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> B2HttpResponse: ...


class UrllibB2Transport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> B2HttpResponse:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return B2HttpResponse(
                    status=int(response.status),
                    body=response.read(),
                    headers={key.lower(): value for key, value in response.headers.items()},
                )
        except HTTPError as exc:
            return B2HttpResponse(
                status=int(exc.code),
                body=exc.read(),
                headers={key.lower(): value for key, value in exc.headers.items()},
            )
        except URLError as exc:
            raise CheckpointBackendError("Backblaze B2 transport failed") from exc


class BackblazeB2ApiError(CheckpointBackendError):
    def __init__(self, *, operation: str, status: int, code: str) -> None:
        self.operation = operation
        self.status = status
        self.code = code
        super().__init__(
            f"Backblaze B2 {operation} failed: HTTP {status}; code={code or 'unknown'}"
        )


@dataclass(frozen=True, slots=True)
class B2AllowedBucket:
    bucket_id: str
    bucket_name: str | None


@dataclass(frozen=True, slots=True)
class B2Authorization:
    account_id: str
    api_url: str
    download_url: str
    authorization_token: str = field(repr=False)
    capabilities: frozenset[str] = frozenset()
    allowed_buckets: tuple[B2AllowedBucket, ...] = ()
    name_prefix: str | None = None


@dataclass(frozen=True, slots=True)
class B2BucketState:
    bucket_id: str
    bucket_name: str
    bucket_type: str
    revision: int
    bucket_info: dict[str, str]
    lifecycle_rules: tuple[dict[str, object], ...]
    replication_enabled: bool


@dataclass(frozen=True, slots=True)
class B2UploadTarget:
    upload_url: str
    authorization_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class B2UploadedFile:
    file_id: str
    file_name: str
    content_sha1: str
    content_length: int


@dataclass(frozen=True, slots=True)
class _B2Context:
    data_auth: B2Authorization
    pointer_auth: B2Authorization
    bucket: B2BucketState
    provider_evidence: BackblazeB2ProviderEvidence


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_response(response: B2HttpResponse, *, operation: str) -> dict[str, object]:
    try:
        payload = json.loads(response.body.decode("utf-8")) if response.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    if response.status >= 400:
        code = str(payload.get("code", "")) if isinstance(payload, dict) else ""
        if response.status == 403 and code in {
            "storage_cap_exceeded",
            "transaction_cap_exceeded",
        }:
            raise CheckpointBackendQuotaError(
                f"Backblaze B2 {operation} blocked by configured zero-cost cap"
            )
        if response.status == 409 and code == "conflict":
            raise CheckpointBackendConflictError(
                "Backblaze B2 bucket revision changed; publish rejected"
            )
        raise BackblazeB2ApiError(operation=operation, status=response.status, code=code)
    if not isinstance(payload, dict):
        raise CheckpointBackendError(f"Backblaze B2 {operation} returned invalid JSON")
    return payload

def _int_field(payload: dict[str, object], name: str, default: int = -1) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default



def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHECKPOINT_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _replication_enabled(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    value = raw.get("value", raw)
    if not isinstance(value, dict):
        return False
    destination = value.get("asReplicationDestination")
    if isinstance(destination, dict) and destination:
        return True
    source = value.get("asReplicationSource")
    if not isinstance(source, dict):
        return False
    rules = source.get("replicationRules")
    if not isinstance(rules, list):
        return False
    return any(isinstance(rule, dict) and bool(rule.get("isEnabled")) for rule in rules)


def _allowed_bucket_matches(
    authorization: B2Authorization,
    *,
    bucket_id: str,
    bucket_name: str,
) -> bool:
    return len(authorization.allowed_buckets) == 1 and authorization.allowed_buckets[0] == (
        B2AllowedBucket(bucket_id=bucket_id, bucket_name=bucket_name)
    )


class BackblazeB2NativeClient:
    def __init__(
        self,
        *,
        transport: B2Transport | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.transport = transport or UrllibB2Transport()
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        operation: str,
    ) -> B2HttpResponse:
        return self.transport.request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            timeout_seconds=self.timeout_seconds,
        )

    def authorize(self, *, key_id: str, application_key: str) -> B2Authorization:
        normalized_id = key_id.strip()
        normalized_key = application_key.strip()
        if not normalized_id or not normalized_key:
            raise ValueError("Backblaze B2 credentials must be non-empty")
        basic = base64.b64encode(
            f"{normalized_id}:{normalized_key}".encode()
        ).decode("ascii")
        response = self._request(
            method="GET",
            url=B2_AUTHORIZE_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {basic}",
                "User-Agent": "SPORTS_EDGE_AI/0.1",
            },
            body=None,
            operation="authorize_account",
        )
        payload = _json_response(response, operation="authorize_account")
        api_info = payload.get("apiInfo")
        if not isinstance(api_info, dict):
            raise CheckpointBackendError("Backblaze B2 authorize response is missing apiInfo")
        storage_api = api_info.get("storageApi")
        if not isinstance(storage_api, dict):
            raise CheckpointBackendError(
                "Backblaze B2 authorize response is missing storageApi"
            )
        allowed = storage_api.get("allowed")
        if not isinstance(allowed, dict):
            raise CheckpointBackendError("Backblaze B2 authorize response is missing allowed")

        allowed_buckets: list[B2AllowedBucket] = []
        raw_buckets = allowed.get("buckets")
        if isinstance(raw_buckets, list):
            for raw in raw_buckets:
                if not isinstance(raw, dict):
                    continue
                bucket_id = raw.get("id")
                if not isinstance(bucket_id, str):
                    continue
                name = raw.get("name")
                allowed_buckets.append(
                    B2AllowedBucket(
                        bucket_id=bucket_id,
                        bucket_name=name if isinstance(name, str) else None,
                    )
                )

        capabilities = allowed.get("capabilities")
        return B2Authorization(
            account_id=str(payload.get("accountId", "")),
            api_url=str(storage_api.get("apiUrl", "")).rstrip("/"),
            download_url=str(storage_api.get("downloadUrl", "")).rstrip("/"),
            authorization_token=str(payload.get("authorizationToken", "")),
            capabilities=frozenset(
                item for item in capabilities if isinstance(item, str)
            )
            if isinstance(capabilities, list)
            else frozenset(),
            allowed_buckets=tuple(allowed_buckets),
            name_prefix=(
                str(allowed["namePrefix"])
                if isinstance(allowed.get("namePrefix"), str)
                else None
            ),
        )

    def list_bucket(
        self,
        authorization: B2Authorization,
        *,
        bucket_id: str,
    ) -> B2BucketState:
        response = self._request(
            method="POST",
            url=f"{authorization.api_url}/b2api/v4/b2_list_buckets",
            headers={
                "Accept": "application/json",
                "Authorization": authorization.authorization_token,
                "Content-Type": "application/json",
            },
            body=_json_bytes(
                {
                    "accountId": authorization.account_id,
                    "bucketId": bucket_id,
                    "bucketTypes": ["all"],
                }
            ),
            operation="list_buckets",
        )
        payload = _json_response(response, operation="list_buckets")
        buckets = payload.get("buckets")
        if not isinstance(buckets, list) or len(buckets) != 1 or not isinstance(
            buckets[0], dict
        ):
            raise CheckpointBackendError("Backblaze B2 expected exactly one configured bucket")
        raw = buckets[0]
        raw_info = raw.get("bucketInfo")
        raw_lifecycle = raw.get("lifecycleRules")
        return B2BucketState(
            bucket_id=str(raw.get("bucketId", "")),
            bucket_name=str(raw.get("bucketName", "")),
            bucket_type=str(raw.get("bucketType", "")),
            revision=int(raw.get("revision", -1)),
            bucket_info={
                str(key): str(value)
                for key, value in raw_info.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            if isinstance(raw_info, dict)
            else {},
            lifecycle_rules=tuple(
                rule for rule in raw_lifecycle if isinstance(rule, dict)
            )
            if isinstance(raw_lifecycle, list)
            else (),
            replication_enabled=_replication_enabled(raw.get("replicationConfiguration")),
        )

    def get_upload_target(
        self,
        authorization: B2Authorization,
        *,
        bucket_id: str,
    ) -> B2UploadTarget:
        response = self._request(
            method="GET",
            url=(
                f"{authorization.api_url}/b2api/v4/b2_get_upload_url?"
                + urlencode({"bucketId": bucket_id})
            ),
            headers={
                "Accept": "application/json",
                "Authorization": authorization.authorization_token,
            },
            body=None,
            operation="get_upload_url",
        )
        payload = _json_response(response, operation="get_upload_url")
        return B2UploadTarget(
            upload_url=str(payload.get("uploadUrl", "")),
            authorization_token=str(payload.get("authorizationToken", "")),
        )

    def upload_checkpoint(
        self,
        target: B2UploadTarget,
        *,
        source: Path,
        object_name: str,
        checkpoint_sha256: str,
    ) -> B2UploadedFile:
        payload = source.read_bytes()
        content_sha1 = hashlib.sha1(payload, usedforsecurity=False).hexdigest()
        response = self._request(
            method="POST",
            url=target.upload_url,
            headers={
                "Authorization": target.authorization_token,
                "Content-Length": str(len(payload)),
                "Content-Type": "application/zip",
                "X-Bz-Content-Sha1": content_sha1,
                "X-Bz-File-Name": quote(object_name, safe="/"),
                "X-Bz-Info-checkpoint-sha256": checkpoint_sha256,
            },
            body=payload,
            operation="upload_file",
        )
        result = _json_response(response, operation="upload_file")
        uploaded = B2UploadedFile(
            file_id=str(result.get("fileId", "")),
            file_name=str(result.get("fileName", "")),
            content_sha1=str(result.get("contentSha1", "")),
            content_length=_int_field(result, "contentLength"),
        )
        if (
            uploaded.file_name != object_name
            or uploaded.content_sha1 != content_sha1
            or uploaded.content_length != len(payload)
            or not uploaded.file_id
        ):
            raise CheckpointBackendError("Backblaze B2 upload verification failed")
        return uploaded

    def update_bucket_info(
        self,
        authorization: B2Authorization,
        *,
        bucket: B2BucketState,
        bucket_info: dict[str, str],
    ) -> B2BucketState:
        response = self._request(
            method="POST",
            url=f"{authorization.api_url}/b2api/v4/b2_update_bucket",
            headers={
                "Accept": "application/json",
                "Authorization": authorization.authorization_token,
                "Content-Type": "application/json",
            },
            body=_json_bytes(
                {
                    "bucketId": bucket.bucket_id,
                    "bucketInfo": bucket_info,
                    "ifRevisionIs": bucket.revision,
                }
            ),
            operation="update_bucket",
        )
        payload = _json_response(response, operation="update_bucket")
        raw_info = payload.get("bucketInfo")
        raw_lifecycle = payload.get("lifecycleRules")
        return B2BucketState(
            bucket_id=str(payload.get("bucketId", "")),
            bucket_name=str(payload.get("bucketName", "")),
            bucket_type=str(payload.get("bucketType", "")),
            revision=_int_field(payload, "revision"),
            bucket_info={
                str(key): str(value)
                for key, value in raw_info.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            if isinstance(raw_info, dict)
            else {},
            lifecycle_rules=tuple(
                rule for rule in raw_lifecycle if isinstance(rule, dict)
            )
            if isinstance(raw_lifecycle, list)
            else (),
            replication_enabled=_replication_enabled(
                payload.get("replicationConfiguration")
            ),
        )

    def download_file_by_id(
        self,
        authorization: B2Authorization,
        *,
        file_id: str,
    ) -> bytes:
        response = self._request(
            method="GET",
            url=(
                f"{authorization.download_url}/b2api/v4/b2_download_file_by_id?"
                + urlencode({"fileId": file_id})
            ),
            headers={"Authorization": authorization.authorization_token},
            body=None,
            operation="download_file",
        )
        if response.status >= 400:
            _json_response(response, operation="download_file")
        expected_sha1 = response.headers.get("x-bz-content-sha1")
        actual_sha1 = hashlib.sha1(
            response.body,
            usedforsecurity=False,
        ).hexdigest()
        if not expected_sha1 or expected_sha1 != actual_sha1:
            raise CheckpointBackendError("Backblaze B2 download SHA1 verification failed")
        return response.body


def manual_evidence_from_settings(settings: Settings) -> BackblazeB2ManualEvidence:
    return BackblazeB2ManualEvidence(
        no_payment_method_confirmed=settings.backblaze_b2_no_payment_method_confirmed,
        zero_dollar_storage_cap_confirmed=(
            settings.backblaze_b2_zero_dollar_storage_cap_confirmed
        ),
        zero_dollar_download_cap_confirmed=(
            settings.backblaze_b2_zero_dollar_download_cap_confirmed
        ),
        transaction_caps_confirmed=settings.backblaze_b2_transaction_caps_confirmed,
    )


def _secret(settings_value: object) -> str:
    if settings_value is None:
        return ""
    getter = getattr(settings_value, "get_secret_value", None)
    return getter().strip() if callable(getter) else str(settings_value).strip()


class BackblazeB2CheckpointBackend:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: B2Transport | None = None,
        timeout_seconds: float = 20.0,
        max_checkpoint_bytes: int = B2_DEFAULT_MAX_CHECKPOINT_BYTES,
    ) -> None:
        if max_checkpoint_bytes <= 0:
            raise ValueError("max_checkpoint_bytes must be positive")
        self.settings = settings or Settings()
        self.client = BackblazeB2NativeClient(
            transport=transport,
            timeout_seconds=timeout_seconds,
        )
        self.max_checkpoint_bytes = max_checkpoint_bytes
        self._last_assessment: BackblazeB2PreflightAssessment | None = None

    def _configured(self) -> bool:
        return all(
            (
                _secret(self.settings.backblaze_b2_key_id),
                _secret(self.settings.backblaze_b2_application_key),
                _secret(self.settings.backblaze_b2_pointer_key_id),
                _secret(self.settings.backblaze_b2_pointer_application_key),
                (self.settings.backblaze_b2_bucket_id or "").strip(),
                (self.settings.backblaze_b2_bucket_name or "").strip(),
            )
        )

    def _context(self) -> _B2Context | None:
        if not self._configured():
            return None
        bucket_id = str(self.settings.backblaze_b2_bucket_id).strip()
        bucket_name = str(self.settings.backblaze_b2_bucket_name).strip()
        expected_prefix = self.settings.backblaze_b2_name_prefix.strip()
        if not expected_prefix or not expected_prefix.endswith("/"):
            raise ValueError("Backblaze B2 name prefix must be a non-empty folder prefix")

        data_auth = self.client.authorize(
            key_id=_secret(self.settings.backblaze_b2_key_id),
            application_key=_secret(self.settings.backblaze_b2_application_key),
        )
        pointer_auth = self.client.authorize(
            key_id=_secret(self.settings.backblaze_b2_pointer_key_id),
            application_key=_secret(self.settings.backblaze_b2_pointer_application_key),
        )
        bucket = self.client.list_bucket(data_auth, bucket_id=bucket_id)
        if bucket.bucket_id != bucket_id or bucket.bucket_name != bucket_name:
            raise CheckpointBackendError("Backblaze B2 configured bucket identity mismatch")

        data_caps = data_auth.capabilities
        pointer_caps = pointer_auth.capabilities
        keys_same_account = data_auth.account_id == pointer_auth.account_id
        provider = BackblazeB2ProviderEvidence(
            credentials_configured=True,
            bucket_configured=True,
            bucket_private=bucket.bucket_type == "allPrivate",
            lifecycle_rules_absent=not bucket.lifecycle_rules,
            cloud_replication_disabled=not bucket.replication_enabled,
            data_key_bucket_scoped=_allowed_bucket_matches(
                data_auth,
                bucket_id=bucket_id,
                bucket_name=bucket_name,
            ),
            data_key_prefix_scoped=data_auth.name_prefix == expected_prefix,
            data_key_capabilities_minimal=(
                _DATA_REQUIRED_CAPABILITIES.issubset(data_caps)
                and data_caps.issubset(_DATA_ALLOWED_CAPABILITIES)
            ),
            pointer_key_capabilities_minimal=(
                _POINTER_REQUIRED_CAPABILITIES.issubset(pointer_caps)
                and pointer_caps.issubset(_POINTER_ALLOWED_CAPABILITIES)
                and not pointer_auth.name_prefix
            ),
            pointer_key_account_wide=not pointer_auth.allowed_buckets,
            keys_same_account=keys_same_account,
            pointer_key_account_wide_required=True,
            provider_round_trip_verified=False,
        )
        return _B2Context(
            data_auth=data_auth,
            pointer_auth=pointer_auth,
            bucket=bucket,
            provider_evidence=provider,
        )

    def preflight(
        self,
        *,
        provider_round_trip_verified: bool = False,
    ) -> BackblazeB2PreflightAssessment:
        context = self._context()
        provider = (
            BackblazeB2ProviderEvidence()
            if context is None
            else replace(
                context.provider_evidence,
                provider_round_trip_verified=provider_round_trip_verified,
            )
        )
        assessment = assess_backblaze_b2_preflight(
            manual=manual_evidence_from_settings(self.settings),
            provider=provider,
        )
        self._last_assessment = assessment
        return assessment

    @property
    def capabilities(self) -> CheckpointBackendCapabilities:
        if self._last_assessment is None:
            return assess_backblaze_b2_preflight(
                manual=manual_evidence_from_settings(self.settings),
                provider=BackblazeB2ProviderEvidence(
                    credentials_configured=self._configured(),
                ),
            ).backend_capabilities
        return self._last_assessment.backend_capabilities

    def _require_storage_context(self) -> _B2Context:
        context = self._context()
        if context is None:
            raise CheckpointBackendError("Backblaze B2 credentials/bucket are not configured")
        assessment = assess_backblaze_b2_preflight(
            manual=manual_evidence_from_settings(self.settings),
            provider=context.provider_evidence,
        )
        self._last_assessment = assessment
        if not assessment.storage_operations_allowed:
            raise CheckpointBackendError(
                "Backblaze B2 zero-cost storage preflight is blocked: "
                + ",".join(assessment.blockers)
            )
        return context

    def _pointer(self, bucket: B2BucketState) -> dict[str, object] | None:
        raw = bucket.bucket_info.get(B2_POINTER_INFO_KEY)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CheckpointBackendError("Backblaze B2 current pointer JSON is invalid") from exc
        if not isinstance(payload, dict):
            raise CheckpointBackendError("Backblaze B2 current pointer is invalid")
        object_name = payload.get("object_name")
        sha256 = payload.get("sha256")
        file_id = payload.get("file_id")
        size = payload.get("bytes")
        prefix = self.settings.backblaze_b2_name_prefix
        if (
            not isinstance(object_name, str)
            or not object_name.startswith(prefix)
            or ".." in object_name.split("/")
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or not isinstance(file_id, str)
            or not file_id
            or not isinstance(size, int)
            or size < 0
        ):
            raise CheckpointBackendError("Backblaze B2 current pointer fields are invalid")
        return payload

    def latest(self) -> StoredCheckpoint | None:
        context = self._require_storage_context()
        pointer = self._pointer(context.bucket)
        if pointer is None:
            return None
        return StoredCheckpoint(
            backend_id=B2_BACKEND_ID,
            generation=str(context.bucket.revision),
            sha256=str(pointer["sha256"]),
            bytes=_int_field(pointer, "bytes", 0),
            object_name=str(pointer["object_name"]),
        )

    def publish(
        self,
        checkpoint_path: Path,
        *,
        expected_generation: str | None,
    ) -> StoredCheckpoint:
        source = checkpoint_path.expanduser().resolve()
        verification = verify_operational_checkpoint(source)
        if source.stat().st_size > self.max_checkpoint_bytes:
            raise CheckpointBackendQuotaError(
                "checkpoint exceeds conservative zero-cost single-file size limit"
            )
        context = self._require_storage_context()
        current_pointer = self._pointer(context.bucket)
        current_generation = (
            None if current_pointer is None else str(context.bucket.revision)
        )
        if current_generation != expected_generation:
            raise CheckpointBackendConflictError(
                "Backblaze B2 checkpoint generation changed; publish rejected"
            )

        object_name = (
            f"{self.settings.backblaze_b2_name_prefix}checkpoints/{verification.sha256}.zip"
        )
        upload_target = self.client.get_upload_target(
            context.data_auth,
            bucket_id=context.bucket.bucket_id,
        )
        uploaded = self.client.upload_checkpoint(
            upload_target,
            source=source,
            object_name=object_name,
            checkpoint_sha256=verification.sha256,
        )
        pointer_payload = {
            "schema_version": "backblaze-b2-checkpoint-pointer-v1",
            "file_id": uploaded.file_id,
            "object_name": object_name,
            "sha256": verification.sha256,
            "bytes": source.stat().st_size,
        }
        new_bucket_info = dict(context.bucket.bucket_info)
        new_bucket_info[B2_POINTER_INFO_KEY] = json.dumps(
            pointer_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        updated = self.client.update_bucket_info(
            context.pointer_auth,
            bucket=context.bucket,
            bucket_info=new_bucket_info,
        )
        return StoredCheckpoint(
            backend_id=B2_BACKEND_ID,
            generation=str(updated.revision),
            sha256=verification.sha256,
            bytes=source.stat().st_size,
            object_name=object_name,
        )

    def verify_stale_revision_conflict(self) -> None:
        context = self._require_storage_context()
        if context.bucket.revision <= 0:
            raise CheckpointBackendError(
                "Backblaze B2 bucket revision must be positive for CAS probe"
            )
        stale = replace(context.bucket, revision=context.bucket.revision - 1)
        try:
            self.client.update_bucket_info(
                context.pointer_auth,
                bucket=stale,
                bucket_info=dict(context.bucket.bucket_info),
            )
        except CheckpointBackendConflictError:
            return
        raise CheckpointBackendError(
            "Backblaze B2 stale revision CAS probe unexpectedly succeeded"
        )

    def fetch_latest(self, destination_dir: Path) -> Path:
        context = self._require_storage_context()
        pointer = self._pointer(context.bucket)
        if pointer is None:
            raise FileNotFoundError("Backblaze B2 has no current checkpoint")
        payload = self.client.download_file_by_id(
            context.data_auth,
            file_id=str(pointer["file_id"]),
        )
        expected_sha256 = str(pointer["sha256"])
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise CheckpointBackendError("Backblaze B2 downloaded checkpoint SHA256 mismatch")

        destination_root = destination_dir.expanduser().resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = destination_root / f"{expected_sha256}.zip"
        with NamedTemporaryFile(
            prefix=".b2-checkpoint-download-",
            suffix=".tmp",
            dir=destination_root,
            delete=False,
        ) as temporary_handle:
            temporary = Path(temporary_handle.name)
            temporary_handle.write(payload)
        try:
            verify_operational_checkpoint(temporary)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination
