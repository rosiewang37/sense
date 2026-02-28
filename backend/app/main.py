"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
import app.models  # noqa: F401 — registers all ORM models in mapper registry at startup
from app.api.auth import router as auth_router
from app.api.webhooks import router as webhooks_router
from app.api.knowledge import router as knowledge_router
from app.api.chat import router as chat_router
from app.api.integrations import router as integrations_router

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start APScheduler for periodic correlation
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.sense.tasks import run_correlation_async

        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_correlation_async, "interval", seconds=120, id="correlation-scan")
        scheduler.start()
        logger.info("APScheduler started: correlation scan every 2 minutes")
    except Exception as e:
        logger.warning(f"APScheduler not started: {e}")

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown(wait=False)
    from app.database import get_engine
    await get_engine().dispose()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(webhooks_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(integrations_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """Database connectivity check."""
    result = await db.execute(text("SELECT 1"))
    result.scalar()
    return {"status": "ok", "database": "connected"}
