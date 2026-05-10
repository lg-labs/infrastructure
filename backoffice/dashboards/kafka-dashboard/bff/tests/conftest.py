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
    InvalidPartitions as DInvalidPartitions,
    KafkaUnavailable,
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
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_kafka() -> FakeKafkaRepo:
    return FakeKafkaRepo()


@pytest.fixture
def app_client(tmp_path, monkeypatch, fake_kafka):
    """Build the FastAPI app with a tmp SQLite + fake Kafka repo."""
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

    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Identity helpers — see helpers.py (kept here for backwards compatibility)
# ---------------------------------------------------------------------------

from .helpers import headers_for  # noqa: E402,F401
