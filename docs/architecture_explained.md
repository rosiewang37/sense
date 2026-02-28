# Sense — Architecture Explained

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  External Services                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────┐ │
│  │  Slack   │  │  GitHub  │  │  Backboard API (LLM gateway) │ │
│  │ Events   │  │ Webhooks │  │  Gemini Flash / Gemini Pro   │ │
│  └────┬─────┘  └────┬─────┘  └──────────────┬───────────────┘ │
└───────│─────────────│────────────────────────│─────────────────┘
        │ webhooks    │ webhooks                │ HTTP (httpx)
        ▼             ▼                         │
┌───────────────────────────┐                  │
│  Backend  (FastAPI :8000) │◄─────────────────┘
│                           │
│  app/api/          ←── REST routers (auth, knowledge, chat,    │
│                         webhooks, integrations)                 │
│  app/sense/        ←── Business logic:                         │
│    detection.py         Pre-filter → classify → extract KOs    │
│    correlation.py       Pairwise KO similarity scoring         │
│    tasks.py             Async event pipeline (BackgroundTasks) │
│    agents/              Verification + Investigative agents    │
│    integrations/        Slack & GitHub event parsers           │
│  app/backboard/    ←── Memory / retrieval layer:               │
│    store.py             CRUD for events & KOs                  │
│    embeddings.py        Embed text → 768-dim vectors           │
│    search.py            pgvector similarity search             │
│    llm.py               Backboard API client (all LLM calls)   │
│    models.py            SQLAlchemy ORM models                  │
│  app/models/       ←── App ORM models (users, teams, etc.)     │
│  app/database.py   ←── Async engine + session factory          │
│  app/config.py     ←── Pydantic settings (reads .env)          │
│                           │
│  APScheduler       ←── Runs correlation scan every 2 min       │
└───────────┬───────────────┘
            │ asyncpg (async SQL)
            ▼
┌───────────────────────────┐
│  PostgreSQL 16 + pgvector │
│  (:5433 local / :5432 in  │
│   Docker network)         │
│                           │
│  Tables:                  │
│    teams, projects,       │
│    users, integrations,   │
│    chat_messages          │
│    events                 │
│    knowledge_objects      │
│    knowledge_events       │
│    verification_checks    │
│    knowledge_merges       │
│    alembic_version        │
└───────────────────────────┘

┌───────────────────────────┐
│  Frontend  (Vite :5173)   │
│  React 19 + TailwindCSS   │
│  TanStack Query           │
│                           │
│  /api  → proxied to :8000 │
│  /webhooks → :8000        │
│  /health   → :8000        │
└───────────────────────────┘
```

---

## Folder-by-Folder Explanation

### `backend/`

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app factory. Registers routers, CORS, lifespan (APScheduler startup/shutdown). |
| `app/config.py` | `pydantic-settings` reads env vars + `.env` file. Single source of truth for all config. |
| `app/database.py` | Creates async SQLAlchemy engine + session factory lazily. `get_db()` is the FastAPI dependency. |
| `app/models/` | SQLAlchemy ORM models for app-level entities (Team, Project, User, Integration, ChatMessage). `__init__.py` imports all of them so the mapper registry is complete at startup. |
| `app/api/auth.py` | JWT register/login/me endpoints. Uses `passlib[bcrypt]` (pinned to bcrypt 3.2.2 for passlib compat). |
| `app/api/knowledge.py` | CRUD for Knowledge Objects: list, get, patch, delete, confirm, dismiss, verification checks. |
| `app/api/chat.py` | Streaming SSE endpoint: runs investigative agent, streams steps + final answer. |
| `app/api/webhooks.py` | Receives Slack + GitHub webhooks. Verifies signatures, parses events, dispatches background tasks. |
| `app/api/integrations.py` | Integration management (list, connect, disconnect). |
| `app/backboard/models.py` | ORM models for memory layer: Event, KnowledgeObject, KnowledgeEvent, VerificationCheck, KnowledgeMerge. |
| `app/backboard/store.py` | CRUD functions for events and KOs (store, get, list recent). |
| `app/backboard/embeddings.py` | Calls Backboard API to generate 768-dim text embeddings; serializes to bytes for storage. |
| `app/backboard/search.py` | pgvector cosine similarity search over KO embeddings. |
| `app/backboard/llm.py` | **All LLM calls go here.** Backboard API client: chat completions, tool calls, embeddings. Never import provider SDKs elsewhere. |
| `app/backboard/tools.py` | Tool implementations for agents (search_knowledge, get_event_details, etc.). |
| `app/sense/detection.py` | Three-stage extraction pipeline: regex pre-filter → Gemini Flash classifier → Gemini Flash extractor. |
| `app/sense/correlation.py` | Pairwise KO similarity scoring (embedding cosine + actor overlap + time decay + reference matching). Merges above threshold. |
| `app/sense/tasks.py` | Async event processing pipeline: store event → embed → extract KO → verify. Correlation runs via APScheduler every 2 min. |
| `app/sense/agents/verification.py` | Verification agent: Gemini Flash with function calling, max 10 tool calls, checks KO accuracy against events. |
| `app/sense/agents/investigator.py` | Investigative chat agent: Gemini Pro with function calling, max 8 tool calls, answers user questions from memory. |
| `app/sense/integrations/slack.py` | Parses Slack Events API payloads → normalized event dict. Verifies HMAC signature. |
| `app/sense/integrations/github.py` | Parses GitHub webhook payloads (push, PR, issues, reviews) → normalized event dict. Verifies HMAC signature. |
| `alembic/` | Database migrations. `env.py` imports all models so autogenerate sees every table. Run from inside the backend container. |
| `tests/` | 53 pytest tests using SQLite (no Postgres required). |

### `frontend/`

| Path | Purpose |
|---|---|
| `src/pages/` | ChatPage, KnowledgePage, KnowledgeDetailPage, LoginPage, SettingsPage |
| `src/components/` | Reusable UI: chat bubbles, knowledge cards, settings panels |
| `src/hooks/` | `useChat`, `useKnowledge` — TanStack Query data hooks |
| `src/lib/` | API client (fetch wrapper), TypeScript types |
| `vite.config.ts` | Proxies `/api`, `/webhooks`, `/health` → `http://localhost:8000` |

### `docker-compose.yml`

Two services:
- **`postgres`** — `pgvector/pgvector:pg16` image, port `5433:5432`, volume `pgdata`. Healthcheck on `pg_isready`.
- **`backend`** — built from `./backend/Dockerfile`, port `8000:8000`, volume `./backend:/app` (live reload). Waits for postgres healthcheck.

---

## Data Flow: Slack Message → Knowledge Object

```
1. Slack sends POST /webhooks/slack
2. verify_slack_signature() checks HMAC
3. parse_slack_event() → normalized event dict {source, source_id, content, ...}
4. FastAPI BackgroundTasks dispatches process_event_async()

Background (process_event_async):
5. store_event() — dedup by (source, source_id), INSERT into events
6. generate_embedding(content) → 768-dim vector → stored as bytes
7. run_extraction_pipeline():
   a. pre_filter() — regex checks for decision/change keywords (fast, no LLM)
   b. classify() — Gemini Flash: "is this significant?" → yes/no
   c. extract() — Gemini Flash: "extract type, title, summary, detail, tags"
8. store_knowledge_object() — INSERT into knowledge_objects
9. Link event → KO in knowledge_events
10. run_verification_agent() — Gemini Flash with tools, up to 10 calls
11. store_verification_check() × N — INSERT into verification_checks

Periodic (every 2 min, APScheduler):
12. run_correlation_async() — pairwise cosine+actor+time scoring
13. KOs above threshold → INSERT knowledge_merge, mark merged KO as "merged"
```

## Data Flow: Chat Query

```
1. POST /api/chat {question, project_id}
2. Authenticated via JWT
3. StreamingResponse — async generator
4. run_query_agent():
   a. Gemini 2.5 Pro receives question + tool declarations
   b. Tool loop (max 8 calls):
      - search_knowledge(query) → pgvector similarity search
      - get_event_details(id) → raw event from DB
      - get_verification_status(ko_id) → verification checks
   c. Model responds with final answer text
5. SSE stream: one JSON line per agent step, then final answer
```

---

## Deployment

| Component | Local | Production |
|---|---|---|
| PostgreSQL | Docker (`pgvector/pgvector:pg16`, port 5433) | Railway managed Postgres + pgvector plugin |
| Backend | Docker (port 8000) or `uvicorn app.main:app --reload` | Railway (builds from `backend/Dockerfile`) |
| Frontend | `npm run dev` (port 5173, proxies to backend) | Railway / Vercel |

---

## Config & Environment Variables

Config is in `app/config.py` (Pydantic `BaseSettings`). All values can be set via environment variables or `backend/.env`.

| Variable | Default | Required for |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://sense:sense@localhost:5432/sense` | App runtime |
| `DATABASE_URL_SYNC` | `postgresql://sense:sense@localhost:5432/sense` | Alembic migrations |
| `JWT_SECRET_KEY` | `dev-secret-key-...` | Auth (change in prod!) |
| `BACKBOARD_API_URL` | `https://app.backboard.io/api` | All LLM features |
| `BACKBOARD_API_KEY` | _(empty)_ | All LLM features |
| `SLACK_SIGNING_SECRET` | _(empty)_ | Slack webhook verification |
| `GITHUB_WEBHOOK_SECRET` | _(empty)_ | GitHub webhook verification |
| `ENCRYPTION_KEY` | _(empty)_ | OAuth token encryption |

**Load order:** Docker Compose `environment:` block overrides `.env` file, which overrides `config.py` defaults.

---

## Local Run Commands

### Start the database (Docker)
```bash
docker compose up postgres -d
# Verify:
docker exec sense-postgres-1 psql -U sense -d sense -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```

### Run migrations (first time only, or after model changes)
```bash
# Generate migration (from inside container):
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic revision --autogenerate -m 'description'"
# Apply:
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic upgrade head"
```

### Start the backend

**Option A — Docker (recommended, includes hot-reload):**
```bash
docker compose up backend -d
# Logs:
docker logs -f sense-backend-1
```

**Option B — Local Python (uses backend/.env):**
```bash
cd backend
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux
uvicorn app.main:app --reload --port 8000
```

### Start the frontend
```bash
cd frontend
npm run dev
# Opens at http://localhost:5173
```

### Verify everything is connected
```bash
curl http://localhost:8000/health        # {"status":"ok","service":"Sense"}
curl http://localhost:8000/health/db     # {"status":"ok","database":"connected"}
# Then open http://localhost:5173 — login/register should work
```

---

## Common Failure Modes & Fixes

### Docker engine not running (Windows)
**Symptom:** `docker: error during connect: ... pipe/docker_engine`
**Fix:** Start Docker Desktop. After it's running: `docker compose up -d`

### pgvector extension missing
**Symptom:** `ERROR: type "vector" does not exist`
**Fix:**
```bash
docker exec sense-postgres-1 psql -U sense -d sense -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
The `pgvector/pgvector:pg16` Docker image ships the extension — it just needs to be enabled per-database.

### `No module named 'app'` when running Alembic
**Symptom:** `ModuleNotFoundError: No module named 'app'` during `alembic upgrade head`
**Cause:** Alembic isn't run from the right directory or PYTHONPATH isn't set.
**Fix:** Always run Alembic from inside the Docker container with PYTHONPATH set:
```bash
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic upgrade head"
```

### `No module named 'psycopg2'` when running Alembic
**Symptom:** Alembic fails with psycopg2 import error
**Cause:** `alembic.ini`'s `sqlalchemy.url` defaults to `postgresql://` which requires `psycopg2`. The app uses `asyncpg` but `psycopg2-binary` is needed for Alembic's sync engine.
**Fix:** `psycopg2-binary==2.9.10` is in `requirements.txt` and will be in the Docker image from next build.

### SQLAlchemy mapper crash: `'Team' failed to locate a name`
**Symptom:** Every APScheduler job logs `InvalidRequestError: expression 'Team' failed to locate a name ('Team')`
**Cause:** `User` has `relationship("Team")` but the `Team` class was never imported into the SQLAlchemy registry before the first query.
**Fix:** `app/models/__init__.py` now imports all models; `app/main.py` imports `app.models` at startup so the registry is complete before any query runs.

### `passlib` + bcrypt `ValueError: password cannot be longer than 72 bytes`
**Symptom:** Backend crashes on register/login with bcrypt error
**Cause:** `passlib 1.7.4` is incompatible with `bcrypt >= 4.0.0`. Passlib's internal wrap-bug detection test sends a >72-byte password, and newer bcrypt now raises hard on that.
**Fix:** `requirements.txt` pins `bcrypt==3.2.2`.

### Uvicorn restarts constantly (watchfiles picks up venv changes)
**Symptom:** Logs show hundreds of "WatchFiles detected changes in venv/..." and constant reloads
**Cause:** The local `venv/` directory is inside `backend/` which is volume-mounted into the container.
**Fix:** Dockerfile now includes `--reload-exclude venv`. `.dockerignore` also excludes `venv/` from image builds.

### No tables in database (`relation "users" does not exist`)
**Symptom:** 500 errors on all DB-backed endpoints
**Cause:** Alembic migrations were never run.
**Fix:**
```bash
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic upgrade head"
```

---

## CHANGELOG

| Date | Change | Reason |
|---|---|---|
| 2026-02-27 | `app/models/__init__.py` — import all ORM models | Fix SQLAlchemy mapper crash: `User.team = relationship("Team")` could not resolve `Team` at query time because `Team` was never imported in the app process |
| 2026-02-27 | `app/main.py` — add `import app.models` at startup | Ensures `models/__init__.py` runs early, completing the SQLAlchemy mapper registry before APScheduler fires |
| 2026-02-27 | Ran `CREATE EXTENSION IF NOT EXISTS vector` in the sense database | pgvector was installed in Postgres but not enabled in the `sense` DB |
| 2026-02-27 | Generated and applied initial Alembic migration (`ab6294541034_initial.py`) | No migrations had ever been run; zero tables existed; all DB endpoints returned 500 |
| 2026-02-27 | `requirements.txt` — added `psycopg2-binary==2.9.10` | Alembic's sync engine needs a sync PG driver; only `asyncpg` was listed |
| 2026-02-27 | `requirements.txt` — pinned `bcrypt==3.2.2` | `bcrypt >= 4.0` raises `ValueError` on passwords >72 bytes; passlib 1.7.4's internal test hits this limit |
| 2026-02-27 | `backend/.env` created | No `.env` file existed; required for local-only development outside Docker |
| 2026-02-27 | Recreated `backend/venv/` | Old venv had hardcoded paths to a different project (`backboard`); `pip list` exited with code 1 |
| 2026-02-27 | `backend/.dockerignore` created | No `.dockerignore` existed; `venv/`, `__pycache__`, `.env`, `test.db` were being included in Docker image builds |
| 2026-02-27 | `backend/Dockerfile` — added `--reload-exclude venv` to uvicorn CMD | When local venv is inside `backend/` and volume-mounted, watchfiles saw thousands of venv file changes and restarted uvicorn constantly |
