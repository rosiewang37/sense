"""Shared test fixtures — uses SQLite for testing (no PostgreSQL required)."""
import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override settings BEFORE importing the app — use SQLite for tests
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///./test.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

from app.config import get_settings
from app.database import Base, get_db

# Clear settings cache so test env vars are picked up
get_settings.cache_clear()

# Import all models so Base.metadata knows about them
from app.models.team import Team
from app.models.project import Project
from app.models.user import User
from app.models.integration import Integration
from app.models.chat import ChatMessage
from app.backboard.models import (
    Event, KnowledgeObject, KnowledgeEvent,
    VerificationCheck, KnowledgeMerge,
)

from app.main import app


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    # Remove test database file
    import pathlib
    pathlib.Path("./test.db").unlink(missing_ok=True)


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine):
    """Async HTTP test client with database override."""
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
