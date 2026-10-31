"""FastAPI application factory (spec §12)."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import auth, catalog, internal, payments, preferences, readings
from .config import get_settings
from .core.errors import error_body, install_error_handlers
from .core.logging import setup_logging
from .db.session import get_engine
from .schemas.schemas import OkResponse

logger = logging.getLogger("app.main")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    problems = settings.validate_production()
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url=None if settings.is_production else "/docs",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url] if not settings.is_production else [],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "X-Telegram-Init-Data", "Content-Type"],
    )

    install_error_handlers(app)

    @app.get("/health", response_model=OkResponse)
    @app.get("/healthz", response_model=OkResponse, include_in_schema=False)
    def healthz():
        return {"ok": True}

    @app.get("/ready")
    @app.get("/readyz", include_in_schema=False)
    def readyz():
        try:
            import sqlalchemy as sa
            with get_engine().connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            return {"ok": True}
        except Exception as exc:
            logger.warning("readiness failed: %s", type(exc).__name__)
            # Readiness MUST fail with a non-2xx status so orchestrators/healthchecks react.
            return JSONResponse(status_code=503,
                                content=error_body("unavailable", "Сервис временно недоступен"))

    # Dev convenience: create tables if missing. Alembic owns production migrations.
    from .db.base import Base
    from . import models as _models  # noqa: F401
    if not settings.is_production:
        try:
            Base.metadata.create_all(get_engine())
        except Exception:  # pragma: no cover - readiness endpoint reports DB problems
            logger.warning("create_all skipped; database may be unavailable")

    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(catalog.router, prefix=prefix)
    app.include_router(readings.router, prefix=prefix)
    app.include_router(preferences.router, prefix=prefix)
    app.include_router(payments.premium_router, prefix=prefix)
    app.include_router(payments.payments_router, prefix=prefix)
    app.include_router(internal.router, prefix=prefix)
    return app


app = create_app()
