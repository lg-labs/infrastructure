"""Settings loaded from env vars (see design.md §9.3)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Kafka
    kafka_bootstrap_servers: str = "kafka1:9092,kafka2:9092,kafka3:9092"
    kafka_admin_request_timeout_ms: int = 10_000

    # Schema Registry (used in Phase D)
    schema_registry_url: str = "http://schema-registry:8081"

    # Persistence
    sqlite_path: str = "/data/app.db"

    # Config files
    owners_yaml_path: str = "/app/config/owners.yaml"

    # Logging
    log_level: str = "INFO"

    # Server
    bff_port: int = 8000

    @property
    def bootstrap_list(self) -> list[str]:
        return [s.strip() for s in self.kafka_bootstrap_servers.split(",") if s.strip()]


settings = Settings()
