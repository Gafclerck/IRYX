"""IRYX Application Entry Point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from iryx import __version__
from iryx.analytics.router import router as analytics_router
from iryx.auth.router import router as auth_router
from iryx.cases.router import router as cases_router
from iryx.core.config import get_settings
from iryx.core.exceptions import register_exception_handlers
from iryx.core.logging import setup_logging
from iryx.evidence.router import router as evidence_router
from iryx.gateway.router import router as gateway_router
from iryx.orchestrator.router import router as orchestrator_router
from iryx.organizations.router import router as organizations_router
from iryx.reporting.router import router as reporting_router

logger = logging.getLogger("iryx.main")


class HealthResponse(BaseModel):
    """Schema for health check endpoint response."""

    status: str = "ok"
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing startup and shutdown tasks."""
    settings = get_settings()
    setup_logging(log_level=settings.log_level)
    logger.info(
        "Starting IRYX API",
        extra={
            "context": {
                "app_name": settings.app_name,
                "version": __version__,
                "environment": settings.environment,
            }
        },
    )
    yield
    from iryx.db.session import engine

    engine.dispose()
    logger.info("Stopping IRYX API")


def create_app() -> FastAPI:
    """Application factory for IRYX API."""
    settings = None
    try:
        settings = get_settings()
        cors_origins = settings.cors_origins
    except Exception:
        # Fallback if settings are not loaded during initial import
        cors_origins = ["*"]

    application = FastAPI(
        title="IRYX API",
        version=__version__,
        description=(
            "Plateforme d'investigation numérique (DFIR) et d'analyse de fraudes supervisée par IA"
        ),
        lifespan=lifespan,
    )

    # Register standardized error handlers (Rule 6)
    register_exception_handlers(application)

    # Register CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API Routers
    application.include_router(auth_router)
    application.include_router(organizations_router)
    application.include_router(cases_router)
    application.include_router(evidence_router)
    application.include_router(gateway_router)
    application.include_router(orchestrator_router)
    application.include_router(analytics_router)
    application.include_router(reporting_router)

    # Thin Health Check Endpoint (D-03)
    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Vérification de santé de l'API",
    )
    async def health_check() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    return application


app = create_app()
