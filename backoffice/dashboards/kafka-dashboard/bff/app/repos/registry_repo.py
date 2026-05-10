"""HTTP client for Confluent Schema Registry.

The BFF acts as a thin proxy. Errors from the Registry are mapped to the
domain envelope (design.md §A5) and re-emitted verbatim where the contract
says so (incompatible_schema, invalid_schema).

Reference: https://docs.confluent.io/platform/current/schema-registry/develop/api.html
SR error codes (subset we map explicitly):
  40401 → subject_not_found        (404)
  40402 → schema_version_not_found (404)
  40403 → schema_not_found         (404)
  42201 → invalid_schema           (400)  [malformed AVRO/JSON/PROTOBUF]
  42202 → invalid_schema           (400)  [version is not a valid integer]
  409   → incompatible_schema      (409)  [HTTP status without an explicit code]
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .. import errors as E
from ..settings import settings

log = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 5.0
_CONTENT_TYPE = "application/vnd.schemaregistry.v1+json"


class RegistryRepo:
    """Lazy-connecting HTTP client for the Schema Registry."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.schema_registry_url).rstrip("/")
        self._client: httpx.Client | None = None

    # ---- low level ----------------------------------------------------------

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=_HTTP_TIMEOUT_S,
                headers={"Accept": _CONTENT_TYPE},
            )
        return self._client

    def reset(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    def _request(self, method: str, path: str, *, subject: str | None = None,
                 json: Any = None) -> httpx.Response:
        try:
            resp = self._http().request(method, path, json=json,
                                        headers={"Content-Type": _CONTENT_TYPE} if json is not None else None)
        except httpx.HTTPError as exc:
            self.reset()
            raise E.RegistryUnavailable(f"{type(exc).__name__}: {exc}") from exc

        if resp.status_code < 400:
            return resp

        # Try to parse SR error envelope: {"error_code": <int>, "message": "..."}
        sr_code: int | None = None
        sr_msg = resp.text
        try:
            body = resp.json()
            if isinstance(body, dict):
                sr_code = body.get("error_code")
                sr_msg = body.get("message", sr_msg)
        except Exception:
            pass

        self._raise_mapped(resp.status_code, sr_code, sr_msg, subject)
        return resp  # unreachable, _raise_mapped always raises

    @staticmethod
    def _raise_mapped(http_status: int, sr_code: int | None, sr_msg: str,
                      subject: str | None) -> None:
        # Connection-level
        if http_status >= 500:
            raise E.RegistryUnavailable(f"SR responded {http_status}: {sr_msg}")

        # Schema-specific
        if sr_code == 40401 or (http_status == 404 and "Subject" in sr_msg):
            raise E.SubjectNotFound(subject or "?")
        if sr_code in (40402, 40403):
            raise E.SchemaVersionNotFound(subject or "?", "?")
        if sr_code in (42201, 42202):
            raise E.InvalidSchema(subject or "?", sr_msg, sr_code)

        # Compatibility check
        if http_status == 409:
            raise E.IncompatibleSchema(subject or "?", sr_msg, sr_code)

        # Unprocessable / bad input
        if http_status in (400, 422):
            raise E.InvalidSchema(subject or "?", sr_msg, sr_code)

        # Default catch-all: surface SR text in the envelope
        raise E.DomainError(http_status, "registry_error",
                            f"Schema Registry returned {http_status}",
                            {"subject": subject, "sr_message": sr_msg,
                             "sr_error_code": sr_code})

    # ---- high level ---------------------------------------------------------

    def alive(self) -> bool:
        """Cheap liveness probe used by /api/health."""
        try:
            r = self._http().get("/subjects", timeout=2.0)
            return r.status_code < 500
        except Exception:
            return False

    def list_subjects(self) -> list[str]:
        r = self._request("GET", "/subjects")
        return list(r.json())

    def get_compatibility(self, subject: str) -> str:
        """Return effective compatibility level (subject override or global default)."""
        try:
            r = self._request("GET", f"/config/{subject}", subject=subject)
            return r.json().get("compatibilityLevel", "BACKWARD")
        except E.SubjectNotFound:
            # No subject-level override → fall back to global
            r = self._request("GET", "/config")
            return r.json().get("compatibilityLevel", "BACKWARD")

    def list_versions(self, subject: str) -> list[int]:
        r = self._request("GET", f"/subjects/{subject}/versions", subject=subject)
        return list(r.json())

    def get_version(self, subject: str, version: int | str) -> dict:
        """Return raw {id, version, schema, schemaType}. version may be int or 'latest'."""
        r = self._request("GET", f"/subjects/{subject}/versions/{version}", subject=subject)
        body = r.json()
        # SR omits schemaType when AVRO (default); normalize it.
        body.setdefault("schemaType", "AVRO")
        return body

    def get_latest(self, subject: str) -> dict:
        return self.get_version(subject, "latest")

    def get_all_versions_full(self, subject: str) -> list[dict]:
        """Return list of full version payloads (used by /export and /detail)."""
        versions = self.list_versions(subject)
        return [self.get_version(subject, v) for v in versions]

    def register_schema(self, subject: str, schema_def: str,
                        schema_type: str = "AVRO",
                        references: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {"schema": schema_def, "schemaType": schema_type}
        if references:
            payload["references"] = references
        r = self._request("POST", f"/subjects/{subject}/versions",
                          subject=subject, json=payload)
        body = r.json()
        # SR returns {"id": <int>}; the version is implicit (latest). Look it up:
        latest = self.get_latest(subject)
        return {"id": body["id"], "version": latest["version"]}

    def set_compatibility(self, subject: str, level: str) -> str:
        r = self._request("PUT", f"/config/{subject}",
                          subject=subject, json={"compatibility": level})
        # SR responds with {"compatibility": "<LEVEL>"}
        return r.json().get("compatibility", level)


# ---- module-level singleton (mirrors kafka_repo pattern) -------------------

_registry_repo: RegistryRepo | None = None


def get_registry_repo() -> RegistryRepo:
    global _registry_repo
    if _registry_repo is None:
        _registry_repo = RegistryRepo()
    return _registry_repo
