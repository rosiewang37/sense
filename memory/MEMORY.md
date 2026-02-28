# Sense — Project Memory

## Status (2026-02-27)
All four patches applied. Backend + DB fully running locally.

## Running State
- Docker containers: `sense-postgres-1` (:5433) + `sense-backend-1` (:8000)
- All 11 DB tables exist (incl. alembic_version)
- pgvector 0.8.1 extension enabled in `sense` DB
- Frontend: `cd frontend && npm run dev` → :5173 (not confirmed running but wiring is correct)

## Key Files
- `backend/app/main.py` — FastAPI entry, imports `app.models` at top for mapper registration
- `backend/app/models/__init__.py` — imports all 5 app models (Team/Project/User/Integration/ChatMessage)
- `backend/app/backboard/llm.py` — ALL LLM calls go here (Backboard API client)
- `backend/alembic/versions/ab6294541034_initial.py` — initial migration (all 10 tables)
- `backend/.env` — local dev config (points to Docker postgres on :5433)
- `docs/architecture_explained.md` — full architecture + run commands + failure mode guide

## Fixes Applied
1. **Mapper crash** — `app/models/__init__.py` now imports all models; `main.py` imports `app.models`
2. **Migrations** — ran pgvector `CREATE EXTENSION`, generated + applied initial migration
3. **psycopg2** — added `psycopg2-binary==2.9.10` to requirements.txt for Alembic sync engine
4. **bcrypt compat** — pinned `bcrypt==3.2.2` (passlib 1.7.4 incompatible with bcrypt >= 4.0)
5. **Venv** — recreated from scratch (old one had paths for `backboard` project, not `sense`)
6. **Watchfiles thrash** — Dockerfile adds `--reload-exclude venv`; added `.dockerignore`
7. **`.env`** — created `backend/.env` for local-only dev outside Docker

## Run Commands
```bash
# DB only
docker compose up postgres -d

# Full stack
docker compose up -d

# Migrations (inside container)
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic upgrade head"

# Local backend (no Docker)
cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Tests (no Postgres needed — uses SQLite)
cd backend && pytest tests/ -v --tb=short
```

## Architecture Notes
- `app/backboard/` = memory layer (events, KOs, embeddings, LLM client) — no Slack/GitHub knowledge
- `app/sense/` = application layer (integrations, detection, correlation, agents)
- LLM: Backboard API → Gemini Flash (detection/extraction/verification), Gemini Pro (chat)
- Embeddings: 768-dim (text-embedding-004), stored as bytes in `events.embedding` and `knowledge_objects.embedding`
- APScheduler runs `run_correlation_async` every 2 min (pairwise KO similarity)

## Known Limitations
- Backboard API key needed for LLM features (set `BACKBOARD_API_KEY` in `.env`)
- pgvector extension must be manually enabled after `docker compose up postgres -d` (first time only — done)
- Alembic must be run from inside the container: `docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic ..."`
