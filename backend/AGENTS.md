# Backend — Intent

## Purpose
Python 3.12 FastAPI backend. Async throughout (asyncpg, async SQLAlchemy).

## Scope
All backend code, tests, and migrations.

## Entry Points
- `app/main.py` — FastAPI app, CORS, routes, APScheduler startup
- `app/config.py` — Pydantic `BaseSettings`, reads `.env`
- `app/database.py` — SQLAlchemy async engine, session factory

## Contracts / Invariants
- All route handlers are async
- Database sessions via `async with get_session_factory()() as db:`
- Config accessed via `get_settings()` (cached singleton)
- Background tasks dispatched via `FastAPI.BackgroundTasks`, not Celery
- APScheduler runs periodic jobs (correlation every 120s, Gmail polling every 300s)

## Testing
- Framework: pytest + pytest-asyncio (`asyncio_mode = auto`)
- Database: SQLite in-memory (no Postgres needed)
- LLM calls: mocked via function parameters (`mock_classify_response`, `mock_extract_response`, `mock_llm_tool_calls`)
- Run: `cd backend && pytest tests/ -v --tb=short`
- Fixtures in `tests/conftest.py`: `db_session`, `sample_event`, etc.

## Dependencies
- `requirements.txt` — pinned Python dependencies
- Docker: `pgvector/pgvector:pg16` for production database
- Alembic: uses sync `DATABASE_URL_SYNC` connection string

## Pitfalls
- `flag_modified()` required after JSON column mutations (SQLAlchemy won't detect in-place dict changes)
- Embedding dimension is 768 (Gemini), not 1536 (OpenAI)
- `psycopg2-binary` needed for Alembic sync engine (separate from asyncpg)
- Test DB is SQLite — don't test pgvector-specific features in unit tests
- `passlib` + `bcrypt` version pinning matters for auth
