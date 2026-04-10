# Sense — Application Layer Intent

## Purpose
Application logic: event processing pipeline, knowledge extraction, correlation, integrations, and agents.

## Scope
`app/sense/` and all subdirectories.

## Entry Points
- `tasks.py:process_event_async()` — THE main pipeline entry for all event processing
- `detection.py:run_extraction_pipeline()` — 3-stage knowledge extraction
- `correlation.py:run_correlation_async()` — periodic KO merge (every 120s)
- `integrations/slack.py:parse_slack_event()` — Slack webhook parser
- `integrations/github.py:parse_github_event()` — GitHub webhook parser
- `integrations/gmail.py:parse_gmail_event()` — Gmail message parser

## Contracts / Invariants
- All integration parsers produce the normalized event dict (see root AGENTS.md)
- Detection pipeline: pre-filter (regex) → classify (LLM) → extract (LLM)
- Classification confidence threshold: 0.5 minimum
- Correlation merge threshold: 0.6
- Context linking threshold: 0.04 (text overlap)
- GitHub evidence link threshold: 0.33

## Pipeline Flow
```
Webhook/Poll → parse_*_event() → process_event_async()
  ├─ store_event() (dedup)
  ├─ generate_embedding()
  ├─ _enrich_*_event_context() (source-specific)
  ├─ run_extraction_pipeline()
  │   ├─ pre_filter() → bool
  │   ├─ LLM classify → {is_significant, confidence, type}
  │   └─ LLM extract → {title, summary, detail, tags}
  ├─ If KO produced → store + link + verify
  └─ If no KO → try link to existing KO
      ├─ Slack: _try_update_related_ko() (context link)
      └─ GitHub: _find_and_link_to_existing_decision() (evidence link)
```

## Canonical Patterns
- Integration parsers: pure functions, no side effects, return normalized dict
- Context enrichment: best-effort, never blocks pipeline on failure
- Follow-up detection: regex pattern match + text overlap scoring
- Actor matching: uses both emails AND names (lowercased) for cross-platform correlation

## Anti-Patterns
- Importing LLM SDKs directly (use `backboard/llm.py`)
- Blocking the pipeline on enrichment failures (always best-effort)
- Replacing context_messages wholesale (merge by timestamp dedup)
- Using email-only actor matching (Slack has names, not emails)

## Dependencies
- `app.backboard.store` — event/KO CRUD
- `app.backboard.llm` — LLM calls
- `app.backboard.embeddings` — embedding generation
- `app.backboard.models` — ORM models for queries
