# Sense — Build Instructions for Claude Code

## Project Overview

Sense is a cross-platform engineering memory system with active verification. It ingests events from Slack and GitHub, extracts structured Knowledge Objects, correlates related events across tools, dispatches AI agents to verify implementation, and exposes everything through a chat interface and dashboard.

## Current State

The system is past initial build phases and is now in **iteration mode**. The core pipeline is running:
- Slack + GitHub webhooks receiving events
- Knowledge extraction pipeline (pre-filter → classify → extract)
- Knowledge Objects shown on the frontend Knowledge page
- Chat page exists but needs fixes

**Active docs for reference:**
- **`docs/BACKBOARD_API.md`** — Backboard API reference (authentication, assistants, threads, messages, tool calling, streaming)
- **`docs/TECHNICAL_SPEC.md`** — Architecture, data model, agent system prompts, and tool definitions
- **`docs/PRD.md`** — Product requirements and user flows

## Iteration Development Rules

- Read existing code before modifying it — understand what's there first
- Make targeted, minimal changes — don't refactor beyond what's needed
- Don't break working functionality while fixing something else
- When adding DB columns, always create an Alembic migration in `backend/alembic/versions/`
- Run: `pytest tests/ -v --tb=short` to verify changes don't break tests

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| LLM Gateway | **Backboard API** (external service — routes to Gemini, GPT, etc.) |
| LLM (Detection/Extraction) | **Gemini 2.0 Flash** via Backboard API |
| LLM (Verification Agent) | **Gemini 2.0 Flash** via Backboard API |
| LLM (Chat/Investigative Agent) | **Gemini 2.5 Pro** via Backboard API |
| Embeddings | **Gemini `text-embedding-004`** via Backboard API (768 dimensions) |
| Agent Framework | Google Gemini function calling (native tool-use, no extra framework) |
| Frontend | React 19 + Vite + TailwindCSS + TanStack Query |
| Auth (MVP) | Simple JWT |
| Deployment | Railway |

## Backboard API (LLM Gateway)

All LLM and embedding calls go through the **Backboard API**, an external model-routing service. This abstracts away provider-specific SDKs.

Build an `app/backboard/llm.py` client module that:
- Wraps all LLM calls (classification, extraction, agent execution) through the Backboard API
- Handles model selection: pass the desired model identifier per call
- Handles retries and error responses
- Makes it easy to swap models later without changing application code

Model mapping:
- **Detection/Extraction** (cheap, fast): `gemini-2.0-flash`
- **Verification Agent** (tool-use, moderate reasoning): `gemini-2.0-flash`
- **Investigative Chat Agent** (tool-use, strong reasoning): `gemini-2.5-pro`
- **Embeddings**: `text-embedding-004` (768 dimensions)

**IMPORTANT:** The pgvector column dimension must be `vector(768)` (not 1536) to match Gemini's embedding size.

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

Adapt the agent system prompts and tool definitions from `docs/TECHNICAL_SPEC.md` Sections 7 and 8. The logic is the same — only the SDK/API format changes.

## Agent Safety Caps

- Verification agent: max **10** tool calls per run
- Investigative query agent: max **8** tool calls per query
- These are hard limits. After reaching the cap, the agent returns whatever it has found.

## Build Priority (If Time-Constrained)

Cut from the bottom first:

1. KEEP: Knowledge extraction from Slack messages
2. KEEP: Investigative chat agent with reasoning toggle
3. KEEP: Verification agent
4. KEEP: GitHub integration
5. KEEP: Correlation engine
6. Cut if needed: Knowledge dashboard
7. Cut if needed: User authentication
8. Cut if needed: Integration setup UI
9. Cut if needed: Confirm/dismiss actions
10. Cut if needed: Agent reasoning toggle

## Project Structure

Follow the directory structure in `docs/TECHNICAL_SPEC.md` Section 12 exactly.

## Key Implementation Details

These are in the TECHNICAL_SPEC but are easy to miss:

- **Pre-filter regex patterns** are in Section 5.2 — use these exact patterns
- **LLM prompts** for classification and extraction are in Sections 5.3 and 5.4 (adapt for Gemini format)
- **Correlation weights** and merge threshold are in Section 6.1
- **Verification agent system prompt and tools** are in Section 7 (adapt tool definitions for Gemini function declarations)
- **Query agent system prompt and tools** are in Section 8 (adapt tool definitions for Gemini function declarations)
- **Streaming SSE implementation** for chat is in Section 8.4 (adapt for Gemini streaming)
- **SQL schemas and indexes** are in Section 3 — create via Alembic migrations. Vectors are `vector(768)` to match Gemini embeddings.
- **Webhook signature verification** is required for both Slack and GitHub

## Environment Variables

Create `.env.example` with all required config. Key variables:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `BACKBOARD_API_URL` — Backboard API gateway URL
- `BACKBOARD_API_KEY` — Backboard API authentication key
- `GEMINI_API_KEY` — Fallback: direct Gemini API key if Backboard API is unavailable
- `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`
- `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY` — Fernet key for OAuth token encryption
