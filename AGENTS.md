# Sense — Root Intent

## Purpose
Cross-platform engineering memory system. Ingests events from Slack, GitHub, and Gmail; extracts structured Knowledge Objects; correlates across tools; verifies with AI agents; exposes via chat and dashboard.

## Scope
Entire repository. This file governs all subdirectories unless overridden by a deeper AGENTS.md.

## Entry Points
- **Backend:** `backend/app/main.py` — FastAPI application
- **Frontend:** `frontend/src/main.tsx` — React SPA

## Architecture Boundary (Critical Invariant)
```
app/backboard/  →  Memory/retrieval layer (storage, LLM, search, embeddings)
app/sense/      →  Application layer (detection, correlation, integrations, agents, tasks)
```
- `backboard/` must NEVER import from `sense/`
- `sense/` calls `backboard/` for all storage and LLM operations
- ALL LLM calls go through `backboard/llm.py` — never import provider SDKs elsewhere

## Data Contracts

### Normalized Event Dict
Every integration parser produces this shape:
```python
{
    "source": "slack" | "github" | "gmail",
    "source_id": str,          # Unique within source (message ts, commit sha, email id)
    "event_type": str,         # message, push, pull_request, email, etc.
    "actor_email": str | None,
    "actor_name": str,
    "content": str,
    "metadata": dict,          # Source-specific (channel, repo, thread_id, etc.)
    "raw_payload": dict,
    "occurred_at": str,        # ISO 8601
    "project_id": str | None,
}
```

### Knowledge Object
```python
{
    "type": "decision" | "approval" | "blocker" | "context",
    "title": str,
    "summary": str,
    "detail": {
        "statement": str,
        "rationale": str | None,
        "alternatives_considered": list[str],
        "expected_follow_ups": list[str],
        "related_context": list[dict],  # Linked events/evidence
    },
    "participants": [{"email": str, "name": str, "role": str}],
    "tags": list[str],
    "confidence": float,  # 0.0-1.0
}
```

## Canonical Patterns
- **Dedup:** Events deduplicated by `(source, source_id)` unique constraint
- **JSON mutations:** Always call `flag_modified(obj, "column_name")` after mutating JSON fields
- **Schema changes:** Always via Alembic migration, never raw DDL
- **Embeddings:** 768 dimensions (Gemini text-embedding-004), stored as `LargeBinary`

## Anti-Patterns
- Importing LLM SDKs anywhere except `backboard/llm.py`
- Hardcoding model names outside `backboard/llm.py`
- Using 1536-dim embeddings (wrong provider assumption)
- Mutating JSON columns without `flag_modified()`
- Skipping Alembic for schema changes
