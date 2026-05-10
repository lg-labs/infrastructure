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


# 409
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
