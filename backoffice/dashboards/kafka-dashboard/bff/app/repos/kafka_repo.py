"""Kafka AdminClient wrapper.

All cluster mutations go through here. Maps kafka-python exceptions to
domain exceptions (design.md §7.3).
"""

import logging
from dataclasses import dataclass
from typing import Any

from kafka.admin import (
    ConfigResource,
    ConfigResourceType,
    KafkaAdminClient,
    NewPartitions,
    NewTopic,
)
from kafka.errors import (
    InvalidPartitionsError,
    InvalidReplicationFactorError,
    KafkaError,
    KafkaTimeoutError,
    NoBrokersAvailable,
    TopicAlreadyExistsError,
    UnknownTopicOrPartitionError,
)

from ..errors import (
    InvalidPartitions as DInvalidPartitions,
    InvalidReplicationFactor as DInvalidReplicationFactor,
    KafkaUnavailable,
    TopicAlreadyExists,
    TopicNotFound,
)
from ..settings import settings

log = logging.getLogger(__name__)

# Configs we surface in the UI as "editable"
EDITABLE_CONFIGS = {
    "cleanup.policy",
    "retention.ms",
    "min.insync.replicas",
}

# All configs we read on describe (for completeness)
INTERESTING_CONFIGS = EDITABLE_CONFIGS | {
    "compression.type",
    "max.message.bytes",
    "segment.bytes",
    "segment.ms",
    "delete.retention.ms",
}


@dataclass
class PartitionInfo:
    id: int
    leader: int
    replicas: list[int]
    isr: list[int]


@dataclass
class TopicInfo:
    name: str
    partitions: int
    replication_factor: int
    is_internal: bool
    configs: dict[str, str]
    partition_details: list[PartitionInfo]


class KafkaRepo:
    """Lazily-instantiated AdminClient wrapper. Reconnects on failure."""

    def __init__(self) -> None:
        self._client: KafkaAdminClient | None = None

    def _client_or_connect(self) -> KafkaAdminClient:
        if self._client is None:
            try:
                self._client = KafkaAdminClient(
                    bootstrap_servers=settings.bootstrap_list,
                    client_id="kafka-dashboard-bff",
                    request_timeout_ms=settings.kafka_admin_request_timeout_ms,
                )
            except NoBrokersAvailable as e:
                raise KafkaUnavailable(str(e)) from e
        return self._client

    def reset(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    # ---- read ops ----

    def list_topics(self) -> list[str]:
        try:
            client = self._client_or_connect()
            return sorted(client.list_topics())
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e

    def brokers_alive(self) -> int:
        try:
            client = self._client_or_connect()
            return len(client.describe_cluster()["brokers"])
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e

    def describe_topic(self, name: str) -> TopicInfo:
        try:
            client = self._client_or_connect()
            descs = client.describe_topics([name])
            if not descs:
                raise TopicNotFound(name)
            d = descs[0]
            if d.get("error_code", 0) != 0:
                # 3 = UNKNOWN_TOPIC_OR_PARTITION
                if d["error_code"] == 3:
                    raise TopicNotFound(name)
                raise KafkaError(f"describe_topics error: {d}")

            partitions = d["partitions"]
            partition_details = [
                PartitionInfo(
                    id=p["partition"],
                    leader=p["leader"],
                    replicas=list(p["replicas"]),
                    isr=list(p["isr"]),
                )
                for p in partitions
            ]
            rf = len(partitions[0]["replicas"]) if partitions else 0

            # Read configs
            res = ConfigResource(ConfigResourceType.TOPIC, name)
            cfgs_raw = client.describe_configs([res])
            cfg_dict: dict[str, str] = {}
            try:
                # kafka-python returns a list of DescribeConfigsResponse
                for response in cfgs_raw:
                    for resource in response.resources:
                        # resource: (error_code, error_msg, type, name, configs[])
                        for cfg in resource[4]:
                            cfg_name = cfg[0]
                            cfg_value = cfg[1]
                            if cfg_name in INTERESTING_CONFIGS:
                                cfg_dict[cfg_name] = cfg_value
            except Exception as e:  # pragma: no cover
                log.warning("could not parse configs for %s: %s", name, e)

            return TopicInfo(
                name=name,
                partitions=len(partitions),
                replication_factor=rf,
                is_internal=d.get("is_internal", name.startswith("_")),
                configs=cfg_dict,
                partition_details=partition_details,
            )
        except UnknownTopicOrPartitionError as e:
            raise TopicNotFound(name) from e
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e

    # ---- write ops ----

    def create_topic(
        self,
        name: str,
        partitions: int,
        replication_factor: int,
        configs: dict[str, str],
    ) -> None:
        try:
            client = self._client_or_connect()
            t = NewTopic(
                name=name,
                num_partitions=partitions,
                replication_factor=replication_factor,
                topic_configs=configs,
            )
            client.create_topics([t])
        except TopicAlreadyExistsError as e:
            raise TopicAlreadyExists(name) from e
        except InvalidReplicationFactorError as e:
            try:
                brokers = self.brokers_alive()
            except Exception:
                brokers = 0
            raise DInvalidReplicationFactor(replication_factor, brokers) from e
        except InvalidPartitionsError as e:
            raise DInvalidPartitions(partitions, str(e)) from e
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e

    def alter_configs(self, name: str, configs: dict[str, str]) -> None:
        try:
            client = self._client_or_connect()
            res = ConfigResource(ConfigResourceType.TOPIC, name, configs=configs)
            client.alter_configs([res])
        except UnknownTopicOrPartitionError as e:
            raise TopicNotFound(name) from e
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e

    def increase_partitions(self, name: str, total: int) -> None:
        try:
            client = self._client_or_connect()
            client.create_partitions({name: NewPartitions(total_count=total)})
        except UnknownTopicOrPartitionError as e:
            raise TopicNotFound(name) from e
        except InvalidPartitionsError as e:
            raise DInvalidPartitions(total, str(e)) from e
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e

    def delete_topic(self, name: str) -> None:
        try:
            client = self._client_or_connect()
            client.delete_topics([name])
        except UnknownTopicOrPartitionError as e:
            raise TopicNotFound(name) from e
        except (NoBrokersAvailable, KafkaTimeoutError) as e:
            self.reset()
            raise KafkaUnavailable(str(e)) from e


# Module-level singleton (FastAPI workers reuse it across requests)
_kafka_repo: KafkaRepo | None = None


def get_kafka_repo() -> KafkaRepo:
    global _kafka_repo
    if _kafka_repo is None:
        _kafka_repo = KafkaRepo()
    return _kafka_repo


def is_internal(name: str) -> bool:
    return name.startswith("_")
