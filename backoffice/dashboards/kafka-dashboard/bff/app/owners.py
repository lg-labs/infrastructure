"""Owners YAML loader (requirements.md §7.2).

Behavior:
  - Loaded eagerly at startup. If malformed, raise → BFF exits 1.
  - Re-read on every read (small file, no caching needed).
  - Schema validated with pydantic.

Email validation:
  We deliberately use a permissive regex (not pydantic.EmailStr) because
  lab/internal TLDs like *.local would be rejected by email-validator's
  deliverability checks. The contact field is illustrative, not used for
  delivery.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from .settings import settings


_ID_RE = re.compile(r"^[a-z0-9-]+$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class Owner(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    contact: str = Field(..., min_length=3)

    @field_validator("id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not _ID_RE.fullmatch(v):
            raise ValueError(f"id {v!r} must match {_ID_RE.pattern}")
        return v

    @field_validator("contact")
    @classmethod
    def _contact_format(cls, v: str) -> str:
        if not _EMAIL_RE.fullmatch(v):
            raise ValueError(f"contact {v!r} is not a valid email address")
        return v


class OwnersFile(BaseModel):
    owners: list[Owner] = Field(default_factory=list)

    @field_validator("owners")
    @classmethod
    def _unique_ids(cls, v: list[Owner]) -> list[Owner]:
        ids = [o.id for o in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate owner ids")
        return v


def load_owners(path: str | None = None) -> list[Owner]:
    p = Path(path or settings.owners_yaml_path)
    if not p.exists():
        raise FileNotFoundError(f"owners file not found at {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return OwnersFile.model_validate(data).owners


def list_owner_ids(path: str | None = None) -> list[str]:
    return [o.id for o in load_owners(path)]


def is_valid_owner(owner_id: str, path: str | None = None) -> bool:
    return owner_id in list_owner_ids(path)
