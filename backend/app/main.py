"""FastAPI application entry point."""
import logging
import sys
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

# ---- Logging setup ----
# Without this, all logger.info() calls in the pipeline are silently discarded
# because Python defaults to WARNING level.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
# Quiet down noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start APScheduler for periodic correlation
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.sense.tasks import run_correlation_async, poll_gmail_messages

        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_correlation_async, "interval", seconds=120, id="correlation-scan")
        logger.info("APScheduler started: correlation scan every 2 minutes")

        # Gmail polling (disabled by default — enable via GMAIL_POLL_ENABLED=true)
        if settings.gmail_poll_enabled:
            scheduler.add_job(
                poll_gmail_messages,
                "interval",
                seconds=settings.gmail_poll_interval_seconds,
                id="gmail-poll",
            )
            logger.info(f"Gmail polling enabled: every {settings.gmail_poll_interval_seconds}s")

        scheduler.start()
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


@app.get("/api/debug/pipeline")
async def debug_pipeline(db: AsyncSession = Depends(get_db)):
    """Diagnostic endpoint: shows recent events and KOs to verify the pipeline is working.

    Hit this in your browser at http://localhost:8000/api/debug/pipeline
    """
    from sqlalchemy import select, func
    from app.backboard.models import Event, KnowledgeObject

    # Recent events (last 10)
    ev_result = await db.execute(
        select(Event).order_by(Event.ingested_at.desc()).limit(10)
    )
    recent_events = [
        {
            "id": str(e.id),
            "source": e.source,
            "content_preview": (e.content or "")[:100],
            "actor_name": e.actor_name,
            "ingested_at": e.ingested_at,
            "has_embedding": e.embedding is not None,
            "has_context": bool((e.metadata_ or {}).get("context_messages")),
        }
        for e in ev_result.scalars().all()
    ]

    # Recent KOs (last 10)
    ko_result = await db.execute(
        select(KnowledgeObject).order_by(KnowledgeObject.detected_at.desc()).limit(10)
    )
    recent_kos = [
        {
            "id": str(ko.id),
            "type": ko.type,
            "title": ko.title,
            "status": ko.status,
            "confidence": ko.confidence,
            "detected_at": ko.detected_at,
        }
        for ko in ko_result.scalars().all()
    ]

    # Counts
    ev_count = (await db.execute(select(func.count(Event.id)))).scalar()
    ko_count = (await db.execute(select(func.count(KnowledgeObject.id)))).scalar()

    return {
        "summary": {
            "total_events": ev_count,
            "total_kos": ko_count,
        },
        "recent_events": recent_events,
        "recent_kos": recent_kos,
    }
