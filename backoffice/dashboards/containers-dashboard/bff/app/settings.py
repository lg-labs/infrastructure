"""Settings loaded from env vars (design.md §9.1, §9.2)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Docker
    docker_host: str = "unix:///var/run/docker.sock"
    docker_api_timeout_s: int = 10

    # Persistence
    sqlite_path: str = "/data/app.db"

    # Logging
    log_level: str = "INFO"
    audit_log_path: str = "/var/log/backoffice/containers-dashboard-app.log"

    # Exec WS
    exec_idle_timeout_s: int = 300

    # Server
    bff_port: int = 8000


settings = Settings()
