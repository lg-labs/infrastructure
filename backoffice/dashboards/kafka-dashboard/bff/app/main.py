"""FastAPI application factory for the Kafka Dashboard BFF.

Routes are mounted under /api/*  (the gateway strips the /kafka/ prefix).
"""

import logging
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pythonjsonlogger import jsonlogger

from .errors import DomainError
from .middleware.audit import AuditMiddleware
from .owners import load_owners
from .repos.db import run_migrations
from .routers import acl_metadata, health, meta, schemas, summary, topics
from .settings import settings


# Path donde el BFF escribe el audit log NDJSON consumido por Filebeat
# (volumen compartido `backoffice-audit-logs`, montado como /var/log/backoffice).
# Configurable vía env para tests; default = path real en producción.
AUDIT_LOG_PATH = os.environ.get(
    "KAFKA_DASHBOARD_AUDIT_LOG_PATH",
    "/var/log/backoffice/kafka-dashboard-app.log",
)


def _setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level"},
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # tame noisy libs
    logging.getLogger("kafka").setLevel(logging.WARNING)

    # ---- Audit logger: stdout (heredado del root) + RotatingFileHandler ----
    # El audit logger ya cuelga del root vía logging.getLogger("kafka_dashboard.audit")
    # y propaga al StreamHandler de arriba. Adicionalmente escribimos a un fichero
    # que Filebeat tail-ea (Phase F.1). Si la ruta no existe (p.ej. tests sin
    # volumen), degradamos a sólo-stdout sin abortar.
    audit_logger = logging.getLogger("kafka_dashboard.audit")
    audit_logger.setLevel(logging.INFO)

    try:
        log_dir = os.path.dirname(AUDIT_LOG_PATH)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            AUDIT_LOG_PATH,
            maxBytes=50 * 1024 * 1024,   # 50 MiB
            backupCount=3,
            encoding="utf-8",
        )
        # Filebeat parsea NDJSON: el `message` ya es un JSON producido por el
        # middleware (json.dumps(event)). Para evitar wrapping doble, usamos
        # un formatter trivial que sólo emite el message tal cual.
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        # Reemplaza handlers de fichero previos para que no se dupliquen
        # entre lifespan reloads.
        audit_logger.handlers = [
            h for h in audit_logger.handlers
            if not isinstance(h, logging.handlers.RotatingFileHandler)
        ] + [file_handler]
    except OSError as e:
        # En desarrollo / tests el path no existe — log y seguir.
        logging.getLogger("kafka_dashboard.bff").warning(
            "audit file handler disabled (%s): %s — events go to stdout only",
            AUDIT_LOG_PATH, e,
        )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _setup_logging(settings.log_level)
    log = logging.getLogger("kafka_dashboard.bff")

    # 1) DB migrations (fail-fast)
    run_migrations()
    log.info("sqlite migrations applied (path=%s)", settings.sqlite_path)

    # 2) Owners YAML (fail-fast — see addendum A4)
    owners = load_owners()
    log.info("owners loaded count=%d", len(owners))

    log.info("kafka-dashboard-bff ready (kafka=%s)", settings.kafka_bootstrap_servers)
    yield
    log.info("kafka-dashboard-bff shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kafka Dashboard BFF",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    app.add_middleware(AuditMiddleware)

    # Routers — all under /api
    app.include_router(health.router, prefix="/api")
    app.include_router(meta.router, prefix="/api")
    app.include_router(summary.router, prefix="/api")
    app.include_router(topics.router, prefix="/api")
    app.include_router(schemas.router, prefix="/api")
    app.include_router(acl_metadata.router, prefix="/api")

    # ---- Error handlers (design.md §7.2 envelope) ----
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        # DomainError stores envelope in HTTPException.detail; flatten to top-level
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        logging.getLogger("kafka_dashboard.bff").exception("unhandled: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "internal server error",
                "details": {},
            },
        )

    return app


app = create_app()
