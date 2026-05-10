"""Pytest fixtures.

We do NOT spin up a real Kafka. Instead we:
  - Override settings to point SQLite at a tmp file.
  - Stub out KafkaRepo with an in-memory fake so the routers' contract surface
    is fully testable without a broker.
  - Use FastAPI TestClient for synchronous request/response.
"""

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.errors import (
    IncompatibleSchema,
    InvalidPartitions as DInvalidPartitions,
    InvalidSchema,
    KafkaUnavailable,
    SchemaVersionNotFound,
    SubjectNotFound,
    TopicAlreadyExists,
    TopicNotFound,
)
from app.repos.kafka_repo import PartitionInfo, TopicInfo


# ---------------------------------------------------------------------------
# In-memory fake Kafka repo
# ---------------------------------------------------------------------------

@dataclass
class _FakeTopic:
    name: str
    partitions: int
    replication_factor: int
    configs: dict[str, str] = field(default_factory=dict)


class FakeKafkaRepo:
    """Minimal in-memory KafkaRepo replacement for contract tests."""

    def __init__(self) -> None:
        self.topics: dict[str, _FakeTopic] = {}
        self.alive = True
        # Seed an internal topic + a regular one so list/filter logic is exercised
        self.topics["__consumer_offsets"] = _FakeTopic("__consumer_offsets", 50, 3)
        self.topics["lglabs.seed.events"] = _FakeTopic(
            "lglabs.seed.events", 3, 3,
            configs={"cleanup.policy": "delete", "retention.ms": "604800000",
                     "min.insync.replicas": "2"},
        )

    def _check_alive(self) -> None:
        if not self.alive:
            raise KafkaUnavailable("fake broker is down")

    def list_topics(self) -> list[str]:
        self._check_alive()
        return sorted(self.topics.keys())

    def brokers_alive(self) -> int:
        self._check_alive()
        return 3

    def describe_topic(self, name: str) -> TopicInfo:
        self._check_alive()
        if name not in self.topics:
            raise TopicNotFound(name)
        t = self.topics[name]
        return TopicInfo(
            name=t.name,
            partitions=t.partitions,
            replication_factor=t.replication_factor,
            is_internal=t.name.startswith("_"),
            configs=dict(t.configs),
            partition_details=[
                PartitionInfo(id=i, leader=1, replicas=[1, 2, 3], isr=[1, 2, 3])
                for i in range(t.partitions)
            ],
        )

    def create_topic(self, name, partitions, replication_factor, configs):
        self._check_alive()
        if name in self.topics:
            raise TopicAlreadyExists(name)
        self.topics[name] = _FakeTopic(name, partitions, replication_factor, dict(configs))

    def alter_configs(self, name, configs):
        self._check_alive()
        if name not in self.topics:
            raise TopicNotFound(name)
        self.topics[name].configs.update(configs)

    def increase_partitions(self, name, total):
        self._check_alive()
        if name not in self.topics:
            raise TopicNotFound(name)
        if total <= self.topics[name].partitions:
            raise DInvalidPartitions(total, "must be greater than current")
        self.topics[name].partitions = total

    def delete_topic(self, name):
        self._check_alive()
        if name not in self.topics:
            raise TopicNotFound(name)
        del self.topics[name]


# ---------------------------------------------------------------------------
# In-memory fake Schema Registry repo
# ---------------------------------------------------------------------------

class FakeRegistryRepo:
    """Minimal in-memory Schema Registry replacement for contract tests.

    Models the small subset of the SR API the BFF uses, plus a knob to flip
    "incompatible" registrations to test the §A5 verbatim re-emission.
    """

    GLOBAL_DEFAULT = "BACKWARD"

    def __init__(self) -> None:
        # subject -> list of {id, version, schema, schemaType}
        self._versions: dict[str, list[dict]] = {}
        self._compat: dict[str, str] = {}
        self._next_id = 1
        self.alive_flag = True
        # Toggle: when True, the next register_schema raises IncompatibleSchema.
        self.force_incompatible = False
        # Toggle: when True, the next register_schema raises InvalidSchema.
        self.force_invalid_schema = False

        # Seed one subject so list_subjects has data
        self.register_schema(
            "lglabs.smoke.events-value",
            schema_def='{"type":"record","name":"Smoke","fields":[{"name":"id","type":"string"}]}',
            schema_type="AVRO",
        )

    # ---- helpers ----------------------------------------------------------

    def alive(self) -> bool:
        return self.alive_flag

    def list_subjects(self) -> list[str]:
        return sorted(self._versions.keys())

    def get_compatibility(self, subject: str) -> str:
        return self._compat.get(subject, self.GLOBAL_DEFAULT)

    def list_versions(self, subject: str) -> list[int]:
        if subject not in self._versions:
            raise SubjectNotFound(subject)
        return [v["version"] for v in self._versions[subject]]

    def get_version(self, subject: str, version) -> dict:
        if subject not in self._versions:
            raise SubjectNotFound(subject)
        if version == "latest":
            return dict(self._versions[subject][-1])
        try:
            v_int = int(version)
        except (TypeError, ValueError):
            raise InvalidSchema(subject, "version is not a valid integer", 42202)
        for v in self._versions[subject]:
            if v["version"] == v_int:
                return dict(v)
        raise SchemaVersionNotFound(subject, v_int)

    def get_latest(self, subject: str) -> dict:
        return self.get_version(subject, "latest")

    def get_all_versions_full(self, subject: str) -> list[dict]:
        return [self.get_version(subject, v) for v in self.list_versions(subject)]

    def register_schema(self, subject: str, schema_def: str,
                        schema_type: str = "AVRO",
                        references: list[dict] | None = None) -> dict:
        if self.force_invalid_schema:
            self.force_invalid_schema = False
            raise InvalidSchema(subject, "fake invalid schema body", 42201)
        if self.force_incompatible:
            self.force_incompatible = False
            raise IncompatibleSchema(subject, "fake incompatible schema", None)

        existing = self._versions.setdefault(subject, [])
        next_version = (existing[-1]["version"] + 1) if existing else 1
        record = {
            "id": self._next_id,
            "version": next_version,
            "schema": schema_def,
            "schemaType": schema_type,
        }
        existing.append(record)
        self._next_id += 1
        return {"id": record["id"], "version": record["version"]}

    def set_compatibility(self, subject: str, level: str) -> str:
        self._compat[subject] = level
        return level

    def reset(self) -> None:  # parity with real repo's interface
        pass


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_kafka() -> FakeKafkaRepo:
    return FakeKafkaRepo()


@pytest.fixture
def fake_registry() -> FakeRegistryRepo:
    return FakeRegistryRepo()


@pytest.fixture
def app_client(tmp_path, monkeypatch, fake_kafka, fake_registry):
    """Build the FastAPI app with a tmp SQLite + fake Kafka + fake Schema Registry."""
    sqlite_path = tmp_path / "test.sqlite"
    owners_path = Path(__file__).parent / "fixtures" / "owners.yaml"
    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OWNERS_YAML_PATH", str(owners_path))
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "fake:9092")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    # `settings` is module-level (`settings = Settings()` at import time),
    # so we must rebuild it after env vars are in place.
    import app.settings as settings_mod
    from app.settings import Settings
    settings_mod.settings = Settings()

    # Reset cached SQLite connection (was tied to prior path)
    import app.repos.db as db_mod
    if db_mod._conn is not None:
        try:
            db_mod._conn.close()
        except Exception:
            pass
        db_mod._conn = None

    # Inject the fake kafka repo (used via get_kafka_repo singleton)
    import app.repos.kafka_repo as kr
    kr._kafka_repo = fake_kafka

    # Inject the fake registry repo (used via get_registry_repo singleton)
    import app.repos.registry_repo as rr
    rr._registry_repo = fake_registry

    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Identity helpers — see helpers.py (kept here for backwards compatibility)
# ---------------------------------------------------------------------------

from .helpers import headers_for  # noqa: E402,F401
