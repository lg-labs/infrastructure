"""Domain exceptions and HTTP error envelope.

Error envelope (design.md §7.1):
    {"error": "<code>", "message": "<dev-readable>", "details": {...}}
"""

from fastapi import HTTPException


class DomainError(HTTPException):
    """Base domain exception that serializes to the error envelope."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(status_code=status_code, detail={
            "error": code,
            "message": message,
            "details": details or {},
        })


# 400
class InvalidTopicName(DomainError):
    def __init__(self, name: str, reason: str):
        super().__init__(400, "invalid_topic_name", reason, {"name": name})


class InvalidOwner(DomainError):
    def __init__(self, owner: str, valid_owners: list[str]):
        super().__init__(400, "invalid_owner", "owner must be defined in owners.yaml",
                         {"owner": owner, "valid_owners": valid_owners})


class InvalidPartitions(DomainError):
    def __init__(self, partitions: int, reason: str):
        super().__init__(400, "invalid_partitions", reason, {"partitions": partitions})


class InvalidReplicationFactor(DomainError):
    def __init__(self, rf: int, brokers: int):
        super().__init__(400, "invalid_rf",
                         f"replication_factor {rf} > available brokers {brokers}",
                         {"replication_factor": rf, "brokers_available": brokers})


class InvalidSchema(DomainError):
    """Schema body is malformed (SR error codes 42201/42202)."""

    def __init__(self, subject: str, sr_message: str, sr_error_code: int | None = None):
        super().__init__(400, "invalid_schema", "schema body is malformed",
                         {"subject": subject, "sr_message": sr_message,
                          "sr_error_code": sr_error_code})


class InvalidCompatibilityLevel(DomainError):
    def __init__(self, given: str, allowed: list[str]):
        super().__init__(400, "invalid_compatibility_level",
                         "compatibility_level must be one of the allowed values",
                         {"given": given, "allowed": allowed})


class InvalidPrincipal(DomainError):
    """ACL principal must start with `User:` or `Group:` (design §3.5)."""

    def __init__(self, principal: str):
        super().__init__(400, "invalid_principal",
                         "principal must start with 'User:' or 'Group:'",
                         {"principal": principal})


class InvalidResourcePattern(DomainError):
    """Resource pattern shape doesn't match enum / non-empty rules."""

    def __init__(self, reason: str, **details):
        super().__init__(400, "invalid_resource_pattern", reason, details)


# 403
class InternalTopicProtected(DomainError):
    def __init__(self, name: str):
        super().__init__(403, "internal_topic_protected",
                         "internal topics (prefix __ or _) cannot be modified",
                         {"name": name})


# 404
class TopicNotFound(DomainError):
    def __init__(self, name: str):
        super().__init__(404, "topic_not_found", f"topic {name!r} does not exist", {"name": name})


class SubjectNotFound(DomainError):
    def __init__(self, subject: str):
        super().__init__(404, "subject_not_found",
                         f"schema subject {subject!r} does not exist", {"subject": subject})


class SchemaVersionNotFound(DomainError):
    def __init__(self, subject: str, version: str | int):
        super().__init__(404, "schema_version_not_found",
                         f"version {version!r} of subject {subject!r} does not exist",
                         {"subject": subject, "version": version})


class AclMetadataNotFound(DomainError):
    def __init__(self, acl_id: str):
        super().__init__(404, "acl_metadata_not_found",
                         f"acl-metadata {acl_id!r} does not exist", {"id": acl_id})


# 409
class IncompatibleSchema(DomainError):
    """Re-emitted from Schema Registry verbatim (design §A5)."""

    def __init__(self, subject: str, sr_message: str, sr_error_code: int | None = None):
        super().__init__(409, "incompatible_schema",
                         "schema is incompatible with the configured compatibility level",
                         {"subject": subject, "sr_message": sr_message,
                          "sr_error_code": sr_error_code})


class TopicAlreadyExists(DomainError):
    def __init__(self, name: str):
        super().__init__(409, "topic_already_exists",
                         f"topic {name!r} already exists", {"name": name})


class AclMetadataDuplicate(DomainError):
    """UNIQUE constraint violation on `acl_metadata` (design §7.2)."""

    def __init__(self, principal: str, resource_type: str, resource_name: str,
                 operation: str, permission_type: str):
        super().__init__(
            409, "acl_metadata_duplicate",
            "acl-metadata with the same (principal, host, operation, "
            "resource_type, resource_name, pattern_type, permission_type) "
            "already exists",
            {
                "principal": principal,
                "resource_type": resource_type,
                "resource_name": resource_name,
                "operation": operation,
                "permission_type": permission_type,
            },
        )


class ConfirmationRequired(DomainError):
    def __init__(self, expected: str):
        super().__init__(409, "confirmation_required",
                         "X-Confirm-Resource header missing or does not match resource name",
                         {"expected": expected})


# 503
class KafkaUnavailable(DomainError):
    def __init__(self, reason: str = "no brokers available"):
        super().__init__(503, "kafka_unavailable", reason)


class RegistryUnavailable(DomainError):
    def __init__(self, reason: str):
        super().__init__(503, "registry_unavailable", reason)
