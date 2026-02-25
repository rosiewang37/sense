from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine_and_session(database_url: str, echo: bool = False):
    engine = create_async_engine(database_url, echo=echo)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


def _get_defaults():
    from app.config import get_settings
    settings = get_settings()
    return create_engine_and_session(settings.database_url, settings.debug)


# Lazy initialization — only created when first accessed
_engine = None
_async_session = None


def get_engine():
    global _engine, _async_session
    if _engine is None:
        _engine, _async_session = _get_defaults()
    return _engine


def get_session_factory():
    global _engine, _async_session
    if _async_session is None:
        _engine, _async_session = _get_defaults()
    return _async_session


# Aliases for backward compat
@property
def engine():
    return get_engine()


async def get_db() -> AsyncSession:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
