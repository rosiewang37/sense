# Backboard — Memory/Retrieval Layer Intent

## Purpose
Storage, search, embeddings, and LLM gateway. This is the "memory" of the system — it knows how to store and retrieve data but has NO knowledge of what Slack, GitHub, or Gmail are.

## Scope
`app/backboard/` and all subdirectories.

## Entry Points
- `llm.py` — `backboard_llm` singleton for all LLM/embedding calls
- `store.py` — CRUD for events and knowledge objects
- `search.py` — Vector and keyword search
- `embeddings.py` — Embedding generation and conversion
- `models.py` — SQLAlchemy ORM models
- `tools.py` — Agent tool implementations (search wrappers)

## Contracts / Invariants
- **NEVER import from `app.sense`** — this module must remain integration-agnostic
- All LLM calls use `backboard_llm.chat()` with `model_role` parameter:
  - `"detection"` → Gemini 2.5 Flash
  - `"extraction"` → Gemini 2.5 Flash
  - `"verification"` → Gemini 2.5 Flash
  - `"chat"` → Gemini 2.5 Pro
  - `"embedding"` → text-embedding-004
- Events deduped by `(source, source_id)` unique constraint
- Embeddings are 768-dim, stored as `LargeBinary` (bytes)

## Canonical Patterns
```python
# LLM call
from app.backboard.llm import backboard_llm
response = await backboard_llm.chat(messages, model_role="detection", tools=None)

# Store event (dedup built-in)
from app.backboard.store import store_event
event = await store_event(db, event_data_dict)

# Generate embedding
from app.backboard.embeddings import generate_embedding
embedding_bytes = await generate_embedding("text to embed")
```

## Anti-Patterns
- Importing `slack`, `github`, `gmail`, or any integration module
- Using raw HTTP to call LLM providers (use `backboard_llm`)
- Assuming embedding dimension is anything other than 768
- Creating ORM objects without going through `store.py` functions
