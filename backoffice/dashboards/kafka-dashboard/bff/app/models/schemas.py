"""Pydantic models for Schema Registry-backed schemas (design.md §3.4)."""

from typing import Literal

from pydantic import BaseModel, Field

SchemaType = Literal["AVRO", "JSON", "PROTOBUF"]
CompatibilityLevel = Literal["BACKWARD", "BACKWARD_TRANSITIVE", "FORWARD",
                             "FORWARD_TRANSITIVE", "FULL", "FULL_TRANSITIVE", "NONE"]

ALLOWED_COMPAT_LEVELS = (
    "BACKWARD", "BACKWARD_TRANSITIVE", "FORWARD",
    "FORWARD_TRANSITIVE", "FULL", "FULL_TRANSITIVE", "NONE",
)


class SchemaSubjectSummary(BaseModel):
    subject: str
    latest_version: int
    compatibility_level: str
    schema_type: SchemaType


class SchemaSubjectListResp(BaseModel):
    items: list[SchemaSubjectSummary]
    total: int


class SchemaVersionItem(BaseModel):
    id: int
    version: int
    schema_type: SchemaType
    schema_def: str = Field(..., alias="schema")  # avoid clashing with pydantic .schema() on v1; alias preserves API contract

    model_config = {"populate_by_name": True}


class SubjectDetailResp(BaseModel):
    subject: str
    compatibility_level: str
    versions: list[SchemaVersionItem]


class SchemaVersionDetail(BaseModel):
    version: int
    schema_def: str = Field(..., alias="schema")
    schema_type: SchemaType
    diff_with_previous: str | None = None

    model_config = {"populate_by_name": True}


class RegisterSchemaReq(BaseModel):
    schema_def: str = Field(..., alias="schema", min_length=1)
    schema_type: SchemaType = "AVRO"
    references: list[dict] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class RegisterSchemaResp(BaseModel):
    id: int
    version: int


class CompatibilityConfigReq(BaseModel):
    compatibility_level: CompatibilityLevel


class CompatibilityConfigResp(BaseModel):
    compatibility_level: str
