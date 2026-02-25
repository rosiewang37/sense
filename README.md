# Sense — Cross-Platform Engineering Memory with Active Verification

Sense ingests events from Slack and GitHub, extracts structured Knowledge Objects (decisions, changes, approvals), correlates related events across tools, dispatches AI agents to verify implementation, and exposes everything through a chat interface and dashboard.

## Architecture

```
backend/           Python 3.12+ / FastAPI backend
  app/
    backboard/     Memory & retrieval layer (events, KOs, search, LLM client)
    sense/         Application layer (detection, correlation, agents, integrations)
    api/           REST API routers (auth, chat, knowledge, webhooks)
    models/        Shared SQLAlchemy models (users, teams, projects)
  tests/           53 tests across 7 test files
  alembic/         Database migrations

frontend/          React 19 + Vite + TailwindCSS + TanStack Query
  src/
    pages/         ChatPage, KnowledgePage, KnowledgeDetailPage, LoginPage, SettingsPage
    components/    chat/, knowledge/, settings/
    hooks/         useChat, useKnowledge
    lib/           api client, TypeScript types
```

## Prerequisites

**Always required:**
- **Python 3.12+**
- **Node.js 18+** and npm

**For running tests only:** Nothing else — tests use SQLite, no external services needed.

**For running the full app:**
- **PostgreSQL 16** with [pgvector](https://github.com/pgvector/pgvector) — installed locally or via Docker

**For LLM features:**
- A **Backboard API key** (from [backboard.io](https://backboard.io))

## Quick Start (Tests Only — No Docker Needed)

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
pytest tests/ -v --tb=short   # 53 tests, all pass
```

This runs the full test suite using SQLite. No PostgreSQL or Docker required.

## Full App Setup

### 1. Start PostgreSQL

**Option A — Docker:**

```bash
docker compose up postgres -d
```

**Option B — Local install:**

Install PostgreSQL with pgvector, then create the database:

```sql
CREATE DATABASE sense;
\c sense
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# Copy and configure environment
cp ../.env.example .env
# Edit .env with your database URL, Backboard API key, etc.
```

### 3. Database Migrations

```bash
cd backend

# Run Alembic migrations (requires PostgreSQL running)
alembic upgrade head
```

If you don't have Alembic migrations generated yet, create the initial one:

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 4. Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API is now at **http://localhost:8000**. Check health:

```
GET http://localhost:8000/health
GET http://localhost:8000/health/db
```

Background tasks (event processing, verification) run in-process via FastAPI BackgroundTasks.
Periodic correlation runs automatically via APScheduler (every 2 minutes).

### 5. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend is now at **http://localhost:5173**.

## Running Tests

Tests use SQLite (no PostgreSQL required):

```bash
cd backend
pytest tests/ -v --tb=short
```

Expected output: **53 passed**.

### Test breakdown by phase

| Test File | Phase | Tests |
|---|---|---|
| `test_foundation.py` | 1 — Infrastructure | 7 |
| `test_webhooks.py` | 2 — Webhooks | 6 |
| `test_ingestion.py` | 2 — Ingestion | 2 |
| `test_detection.py` | 3 — Extraction | 12 |
| `test_correlation.py` | 4 — Correlation | 11 |
| `test_verification_agent.py` | 5 — Verification | 7 |
| `test_investigator_agent.py` | 6 — Chat Agent | 5 |
| `test_search.py` | 6 — Search | 3 |

## API Endpoints

```
# Auth
POST   /api/auth/register        Register a new user
POST   /api/auth/login            Login (OAuth2 form)
GET    /api/auth/me               Get current user (protected)

# Knowledge Objects
GET    /api/knowledge             List KOs (filterable by type, status, project)
GET    /api/knowledge/:id         Get KO detail with verification checks
PATCH  /api/knowledge/:id         Update KO (title, status, tags)
DELETE /api/knowledge/:id         Delete KO
POST   /api/knowledge/:id/confirm Human confirms accuracy
POST   /api/knowledge/:id/dismiss Human dismisses false positive
GET    /api/knowledge/:id/verification  Get verification checks

# Chat (SSE streaming)
POST   /api/chat                  Query project memory (streaming agent response)
GET    /api/chat/history          Chat history

# Webhooks (called by external services)
POST   /webhooks/slack            Slack Events API
POST   /webhooks/github           GitHub Webhooks
```

## Environment Variables

Copy `.env.example` to `backend/.env` and configure:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | PostgreSQL sync URL (for Alembic) |
| `JWT_SECRET_KEY` | Secret for JWT token signing |
| `BACKBOARD_API_URL` | Backboard API base URL |
| `BACKBOARD_API_KEY` | Your Backboard API key |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `GITHUB_WEBHOOK_SECRET` | GitHub webhook secret |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Background Tasks | FastAPI BackgroundTasks + APScheduler |
| Database | PostgreSQL 16 + pgvector |
| LLM Gateway | Backboard API |
| LLM (Detection) | Gemini 2.0 Flash |
| LLM (Chat Agent) | Gemini 2.5 Pro |
| Embeddings | Gemini text-embedding-004 (768 dim) |
| Frontend | React 19 + Vite + TailwindCSS + TanStack Query |
| Auth | Simple JWT |
