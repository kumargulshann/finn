from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.db.session import create_database_engine, create_session_factory
from app.api.routes.health import router as health_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.events import router as events_router
from app.api.routes.companies import router as companies_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.admin_refresh import router as announcement_router
from app.services.seed import seed_demo_data
from app.services.market_data import MarketDataService
from app.services.announcement_ingestion import AnnouncementIngestionService
from app.api.routes.research_documents import router as research_router
from app.services.research_documents import ResearchDocumentService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_database_engine(app_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        backend_dir = Path(__file__).resolve().parents[1]
        migration_config = Config(str(backend_dir / "alembic.ini"))
        migration_config.set_main_option(
            "script_location", str(backend_dir / "app" / "db" / "migrations")
        )
        migration_config.set_main_option("sqlalchemy.url", app_settings.database_url)
        command.upgrade(migration_config, "head")
        with session_factory() as session:
            seed_demo_data(session)
        yield
        engine.dispose()

    app = FastAPI(title="FINN API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.market_data = MarketDataService(cache_ttl_seconds=app_settings.market_cache_ttl_seconds)
    app.state.announcement_ingestion = AnnouncementIngestionService()
    app.state.research_documents = ResearchDocumentService()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(health_router)
    app.include_router(portfolio_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(companies_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(announcement_router, prefix="/api/v1")
    app.include_router(research_router, prefix="/api/v1")
    return app


app = create_app()

