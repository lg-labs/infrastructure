"""FastAPI application factory for the Containers Dashboard BFF.

Routes mounted under /api/* (gateway strips /containers/ prefix).
"""
from __future__ import annotations

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
from .repos.db import run_migrations
from .repos.docker_repo import get_docker_repo
from .routers import containers, health, images, networks, projects, summary, volumes
from .routers import exec as exec_router
from .settings import settings


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
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Audit logger: stdout (root) + RotatingFileHandler (Filebeat tails it)
    audit_logger = logging.getLogger("containers_dashboard.audit")
    audit_logger.setLevel(logging.INFO)

    try:
        log_dir = os.path.dirname(settings.audit_log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            settings.audit_log_path,
            maxBytes=50 * 1024 * 1024,   # 50 MiB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.handlers = [
            h for h in audit_logger.handlers
            if not isinstance(h, logging.handlers.RotatingFileHandler)
        ] + [file_handler]
    except OSError as e:
        logging.getLogger("containers_dashboard.bff").warning(
            "audit file handler disabled (%s): %s — events go to stdout only",
            settings.audit_log_path, e,
        )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _setup_logging(settings.log_level)
    log = logging.getLogger("containers_dashboard.bff")

    run_migrations()
    log.info("sqlite migrations applied (path=%s)", settings.sqlite_path)

    repo = get_docker_repo()
    if repo.ping():
        log.info("docker daemon reachable (host=%s)", settings.docker_host)
    else:
        log.warning("docker daemon NOT reachable at %s — endpoints will return 503", settings.docker_host)

    log.info("containers-dashboard-bff ready")
    yield
    log.info("containers-dashboard-bff shutting down")
    repo.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Containers Dashboard BFF",
        version="0.3.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    app.add_middleware(AuditMiddleware)

    # Routers — all under /api
    app.include_router(health.router, prefix="/api")
    app.include_router(summary.router, prefix="/api")
    app.include_router(containers.router, prefix="/api")
    app.include_router(images.router, prefix="/api")
    app.include_router(volumes.router, prefix="/api")
    app.include_router(networks.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(exec_router.router, prefix="/api")

    # ---- Error handlers (design.md §7.1 envelope) ----
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_payload",
                "message": "request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_payload",
                "message": "request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        logging.getLogger("containers_dashboard.bff").exception("unhandled: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "internal server error", "details": {}},
        )

    return app


app = create_app()
