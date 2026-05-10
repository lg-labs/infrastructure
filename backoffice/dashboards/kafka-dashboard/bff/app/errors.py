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
