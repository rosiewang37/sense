# Sense — Build Instructions for Claude Code

## Project Overview

Sense is a cross-platform engineering memory system with active verification. It ingests events from Slack, GitHub, and Gmail, extracts structured Knowledge Objects (decisions, approvals, blockers), correlates related events across tools, dispatches AI agents to verify implementation, and exposes everything through a chat interface and dashboard.

## Directory Map

```
sense/
├── CLAUDE.md                 # This file — build instructions
├── AGENTS.md                 # Root intent layer for AI agents
├── docker-compose.yml        # Local dev (Postgres + Backend)
├── hooks/                    # Self-validation scripts
│
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app entry point
│   │   ├── config.py         # Pydantic Settings, reads .env
│   │   ├── database.py       # SQLAlchemy async engine + sessions
│   │   ├── backboard/        # Memory/retrieval layer (LLM, storage, search, embeddings)
│   │   │   ├── llm.py        # Backboard API LLM gateway client
│   │   │   ├── models.py     # SQLAlchemy models (Event, KnowledgeObject, etc.)
│   │   │   ├── store.py      # CRUD operations
│   │   │   ├── embeddings.py # Gemini 768-dim embeddings
│   │   │   ├── search.py     # Vector/keyword search
│   │   │   └── tools.py      # Agent tool implementations
│   │   ├── sense/            # Application layer (detection, correlation, integrations)
│   │   │   ├── detection.py  # 3-stage extraction pipeline (pre-filter → classify → extract)
│   │   │   ├── correlation.py # Cross-tool correlation engine
│   │   │   ├── tasks.py      # Main event processing pipeline
│   │   │   ├── agents/       # Verification + investigative agents
│   │   │   └── integrations/ # Slack, GitHub, Gmail connectors
│   │   ├── api/              # FastAPI route handlers
│   │   └── models/           # Shared data models (User, Team, Project, etc.)
│   ├── tests/                # pytest test suite
│   ├── alembic/              # Database migrations
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── pages/            # ChatPage, KnowledgePage, KnowledgeDetailPage
│   │   ├── components/       # chat/, knowledge/, settings/ components
│   │   ├── hooks/            # useChat, useKnowledge, useIntegrations
│   │   └── lib/              # api.ts (client), types.ts
│   └── package.json
│
└── docs/                     # TECHNICAL_SPEC, BACKBOARD_API, PRD, etc.
```

## Commands

```bash
# Backend tests (from backend/)
cd backend && pytest tests/ -v --tb=short

# Run backend dev server (from backend/)
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend build (from frontend/)
cd frontend && npm run build

# Frontend type-check (from frontend/)
cd frontend && npx tsc -b

# Frontend lint (from frontend/)
cd frontend && npm run lint

# Frontend dev server (from frontend/)
cd frontend && npm run dev

# Database migrations (via Docker)
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic upgrade head"

# New migration (via Docker)
docker exec sense-backend-1 sh -c "cd /app && PYTHONPATH=/app alembic revision --autogenerate -m 'description'"

# Docker services
docker compose up -d          # Start Postgres + Backend
docker compose up backend -d --build  # Rebuild backend

# Health checks
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/db
```

## Debugging

- **Print-statement debugging** is the established pattern in this codebase. Look for `print(f"[SENSE] ...")` statements throughout `tasks.py` and `slack_api.py`.
- **Structured logging** via Python `logging` module is used alongside prints. Logger name: `logger = logging.getLogger(__name__)`.
- **Common failure modes:**
  - Empty context on KOs → Slack bot token missing or API rate-limited. Check `SLACK_BOT_TOKEN` in `.env`.
  - Embeddings returning None → Backboard API key invalid or service down. Check `BACKBOARD_API_KEY`.
  - `flag_modified` not called → JSON column updates silently lost. Always call `flag_modified(obj, "column_name")` after mutating JSON fields.
  - Embedding dimension mismatch → must be `vector(768)` for Gemini, not 1536.
- **Test debugging:** Tests use SQLite in-memory (no Postgres needed). Mock LLM calls via `mock_classify_response` / `mock_extract_response` / `mock_llm_tool_calls` parameters.

## MCP Servers

Three MCP servers are connected for testing and data access:

- **Slack MCP** — `slack_read_channel`, `slack_search_public`, `slack_send_message`, etc. Use for reading channel history, sending test messages, verifying decision detection.
- **GitHub MCP** — `get_file_contents`, `list_commits`, `search_code`, `pull_request_read`, etc. Use for checking commits, PRs, and verifying cross-platform correlation.
- **Gmail MCP** — `gmail_search_messages`, `gmail_read_message`, `gmail_read_thread`, etc. Use for reading emails, testing Gmail integration polling.

When testing the pipeline end-to-end, use MCP to send/read test data and verify KOs appear correctly.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Task Queue | Background tasks via FastAPI (async) |
| Database | PostgreSQL 16 + pgvector |
| LLM Gateway | **Backboard API** (external service — routes to Gemini, GPT, etc.) |
| LLM (Detection/Extraction) | **Gemini 2.5 Flash** via Backboard API |
| LLM (Verification Agent) | **Gemini 2.5 Flash** via Backboard API |
| LLM (Chat/Investigative Agent) | **Gemini 2.5 Pro** via Backboard API |
| Embeddings | **Gemini `text-embedding-004`** via Backboard API (768 dimensions) |
| Agent Framework | Google Gemini function calling (native tool-use, no extra framework) |
| Frontend | React 19 + Vite + TailwindCSS + TanStack Query |
| Auth (MVP) | Simple JWT |
| Deployment | Railway |

## Architecture Boundary

The codebase has two internal modules (one deployable monolith):

- **`app/backboard/`** — Memory/retrieval layer: event + KO storage, embeddings, vector search, agent tool implementations, CRUD, **LLM gateway client**
- **`app/sense/`** — Application layer: integration connectors, NLP detection, correlation, verification agents, investigative agents, tasks

Keep this separation clean. The Backboard module should have no knowledge of Slack, GitHub, or any specific integration. All LLM calls must go through the Backboard LLM client — never import provider SDKs directly in the Sense layer.

## Agent Implementation (Gemini Function Calling)

Agents use **Gemini function calling** instead of Anthropic tool-use. The patterns are similar:

1. Define tools as function declarations (name, description, parameters)
2. Send messages to the model with tool declarations
3. Model responds with function calls
4. Execute the function, return results
5. Loop until model responds with text (no more function calls) or hits the safety cap

Adapt the agent system prompts and tool definitions from `docs/TECHNICAL_SPEC.md` Sections 7 and 8.

## Agent Safety Caps

- Verification agent: max **10** tool calls per run
- Investigative query agent: max **8** tool calls per query
- These are hard limits. After reaching the cap, the agent returns whatever it has found.

## Key Implementation Details

These are in the TECHNICAL_SPEC but are easy to miss:

- **Pre-filter regex patterns** are in Section 5.2 — use these exact patterns
- **LLM prompts** for classification and extraction are in Sections 5.3 and 5.4 (adapt for Gemini format)
- **Correlation weights** and merge threshold are in Section 6.1
- **Verification agent system prompt and tools** are in Section 7
- **Query agent system prompt and tools** are in Section 8
- **Streaming SSE implementation** for chat is in Section 8.4
- **SQL schemas and indexes** are in Section 3 — create via Alembic migrations. Vectors are `vector(768)` to match Gemini embeddings.
- **Webhook signature verification** is required for both Slack and GitHub

## Iteration Development Rules

- Read existing code before modifying it — understand what's there first
- Make targeted, minimal changes — don't refactor beyond what's needed
- Don't break working functionality while fixing something else
- When adding DB columns, always create an Alembic migration in `backend/alembic/versions/`
- Run: `pytest tests/ -v --tb=short` to verify changes don't break tests

## Environment Variables

Key variables in `.env` (root and `backend/`):
- `DATABASE_URL` — PostgreSQL connection string (asyncpg)
- `DATABASE_URL_SYNC` — PostgreSQL sync connection string (for Alembic)
- `BACKBOARD_API_URL` — Backboard API gateway URL
- `BACKBOARD_API_KEY` — Backboard API authentication key
- `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`
- `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY` — Fernet key for OAuth token encryption

**IMPORTANT:** The pgvector column dimension must be `vector(768)` (not 1536) to match Gemini's embedding size.
