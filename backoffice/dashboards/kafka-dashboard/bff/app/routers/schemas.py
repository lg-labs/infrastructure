"""Schemas router (US-5, US-6, US-9 export).

The BFF is a thin proxy over Schema Registry. We do NOT cache, do NOT alter
schema bodies, and re-emit incompatible_schema verbatim (design §A5).
"""

from __future__ import annotations

import difflib
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ..deps import CurrentUser, require_reader, require_writer
from ..errors import InvalidCompatibilityLevel
from ..models.schemas import (
    ALLOWED_COMPAT_LEVELS,
    CompatibilityConfigReq,
    CompatibilityConfigResp,
    RegisterSchemaReq,
    RegisterSchemaResp,
    SchemaSubjectListResp,
    SchemaSubjectSummary,
    SchemaVersionDetail,
    SchemaVersionItem,
    SubjectDetailResp,
)
from ..repos.registry_repo import get_registry_repo

router = APIRouter(prefix="/schemas", tags=["schemas"])
log = logging.getLogger(__name__)


def _pretty(schema_str: str) -> str:
    """Best-effort JSON pretty-print for the diff. Falls back to raw."""
    try:
        return json.dumps(json.loads(schema_str), indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return schema_str


def _diff(prev: str, curr: str) -> str:
    a = _pretty(prev).splitlines(keepends=False)
    b = _pretty(curr).splitlines(keepends=False)
    return "\n".join(difflib.unified_diff(a, b, fromfile="previous", tofile="current", lineterm=""))


# ---------- LIST SUBJECTS ----------

@router.get("", response_model=SchemaSubjectListResp,
            dependencies=[Depends(require_reader)])
def list_subjects() -> SchemaSubjectListResp:
    repo = get_registry_repo()
    subjects = repo.list_subjects()
    items: list[SchemaSubjectSummary] = []
    for s in subjects:
        try:
            latest = repo.get_latest(s)
            compat = repo.get_compatibility(s)
            items.append(SchemaSubjectSummary(
                subject=s,
                latest_version=int(latest["version"]),
                compatibility_level=compat,
                schema_type=latest.get("schemaType", "AVRO"),
            ))
        except Exception as e:  # one bad subject must not break the list
            log.warning("list_subjects: skipping %s: %s", s, e)
    return SchemaSubjectListResp(items=items, total=len(items))


# ---------- GET SUBJECT ----------

@router.get("/{subject}", response_model=SubjectDetailResp,
            dependencies=[Depends(require_reader)])
def get_subject(subject: str) -> SubjectDetailResp:
    repo = get_registry_repo()
    versions = repo.get_all_versions_full(subject)
    compat = repo.get_compatibility(subject)
    return SubjectDetailResp(
        subject=subject,
        compatibility_level=compat,
        versions=[
            SchemaVersionItem(
                id=int(v["id"]),
                version=int(v["version"]),
                schema_type=v.get("schemaType", "AVRO"),
                **{"schema": v["schema"]},
            )
            for v in versions
        ],
    )


# ---------- GET VERSION ----------

@router.get("/{subject}/versions/{version}", response_model=SchemaVersionDetail,
            dependencies=[Depends(require_reader)])
def get_version(subject: str, version: str) -> SchemaVersionDetail:
    repo = get_registry_repo()
    curr = repo.get_version(subject, version)
    diff: str | None = None
    cv = int(curr["version"])
    if cv > 1:
        try:
            prev = repo.get_version(subject, cv - 1)
            diff = _diff(prev["schema"], curr["schema"])
        except Exception as e:
            log.warning("diff with previous failed (subject=%s v=%d): %s", subject, cv, e)
    return SchemaVersionDetail(
        version=cv,
        schema_type=curr.get("schemaType", "AVRO"),
        diff_with_previous=diff,
        **{"schema": curr["schema"]},
    )


# ---------- REGISTER NEW VERSION ----------

@router.post("/{subject}/versions", response_model=RegisterSchemaResp)
def register_version(
    subject: str,
    req: RegisterSchemaReq,
    user: Annotated[CurrentUser, Depends(require_writer)],
) -> RegisterSchemaResp:
    repo = get_registry_repo()
    out = repo.register_schema(
        subject=subject,
        schema_def=req.schema_def,
        schema_type=req.schema_type,
        references=req.references,
    )
    log.info("schema.register subject=%s by=%s id=%s version=%s",
             subject, user.user or "unknown", out["id"], out["version"])
    return RegisterSchemaResp(id=int(out["id"]), version=int(out["version"]))


# ---------- COMPATIBILITY CONFIG ----------

@router.put("/{subject}/config", response_model=CompatibilityConfigResp)
def set_compatibility(
    subject: str,
    req: CompatibilityConfigReq,
    user: Annotated[CurrentUser, Depends(require_writer)],
) -> CompatibilityConfigResp:
    if req.compatibility_level not in ALLOWED_COMPAT_LEVELS:
        raise InvalidCompatibilityLevel(req.compatibility_level, list(ALLOWED_COMPAT_LEVELS))
    repo = get_registry_repo()
    new_level = repo.set_compatibility(subject, req.compatibility_level)
    log.info("schema.config subject=%s level=%s by=%s", subject, new_level, user.user or "unknown")
    return CompatibilityConfigResp(compatibility_level=new_level)


# ---------- EXPORT (US-9) ----------

@router.get("/{subject}/export", dependencies=[Depends(require_writer)])
def export_subject(subject: str) -> Response:
    repo = get_registry_repo()
    versions = repo.get_all_versions_full(subject)
    compat = repo.get_compatibility(subject)
    payload = {
        "subject": subject,
        "compatibility_level": compat,
        "versions": [
            {
                "id": int(v["id"]),
                "version": int(v["version"]),
                "schema_type": v.get("schemaType", "AVRO"),
                "schema": v["schema"],
            }
            for v in versions
        ],
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{subject}.json"'},
    )
