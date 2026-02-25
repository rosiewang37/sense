# Sense — Development Roadmap

**Version:** 0.3
**Last Updated:** 2026-02-24
**Timeline:** 3–4 day hackathon sprint

---

## Overview

This roadmap is structured in two layers:

1. **Hackathon MVP (3–4 days)** — What to build for the demo (Phases 1–6)
2. **Post-Hackathon** — What to build if the product moves forward (Phases 7–9)

All development follows the **TDD workflow** defined in Phase 0.

---

## Phase 0: Development Workflow (TDD Protocol)

**This phase isn't "built" — it's the protocol followed for all other phases.**

### The Loop

For every feature:

```
1. Write test(s) for the feature
2. Run tests → expect FAIL (confirms test is valid)
3. Implement the feature
4. Run tests → check result
   ├── PASS → mark feature done, move to next feature
   └── FAIL → fix the implementation
               ├── Run tests again
               │   ├── PASS → done
               │   └── FAIL → fix again (attempt 2)
               │               ├── PASS → done
               │               └── FAIL → fix again (attempt 3)
               │                           ├── PASS → done
               │                           └── FAIL → STOP. Log to BLOCKED.md. Move on.
               └──────────────────────────────────────────────────────────────────────────
```

### Infinite Loop Safeguard

| Rule | Detail |
|---|---|
| **Max 3 fix attempts per failing test** | After 3 consecutive failures on the same test, stop trying. |
| **Each attempt must change something** | Submitting identical code counts as a wasted attempt. |
| **Blocked features are logged** | Append to `BLOCKED.md` with: feature name, test file, failure output, and what was tried. |
| **Move on after blocking** | Don't let one stubborn test stall the entire hackathon. Come back later if time allows. |
| **Tests must be independent** | A blocked feature should not prevent other features from being tested. |

### What Gets Tested (Hackathon Scope)

| Must Test (TDD) | Test After (Verification) | Skip Testing (Hackathon) |
|---|---|---|
| Detection pipeline (pre-filter, classification parsing, extraction parsing) | Webhook payload parsing | Frontend components |
| Correlation scoring functions | API endpoint responses | CSS/styling |
| Agent tool functions (search, verification) | Database migrations | Auth flow |
| Agent loop safeguards (max iterations) | | Integration OAuth |
| Merge logic | | |

### Test Tooling

- **Framework:** pytest + pytest-asyncio
- **LLM mocking:** Record real LLM responses once, replay in tests (no live API calls)
- **DB:** Separate test database with fixtures via conftest.py
- **Run command:** `pytest tests/ -v --tb=short`

---

## Phase 1: Foundation & Infrastructure

**Goal:** Deployable backend and frontend skeletons with database and task queue.
**Estimated time:** Half day (Day 1 morning)

### Tasks

- [ ] **1.1** Initialize backend project structure (FastAPI app, config, directory layout per tech spec)
- [ ] **1.2** Set up PostgreSQL with pgvector extension + create Alembic migrations
- [ ] **1.3** Create all SQLAlchemy models (events, knowledge_objects, knowledge_events, verification_checks, projects, teams, users, integrations, chat_messages)
- [ ] **1.4** Set up Redis + Celery (basic worker that processes a test task)
- [ ] **1.5** Initialize frontend project (React + Vite + TailwindCSS + TanStack Query)
- [ ] **1.6** Set up API routing, CORS, and health check endpoint
- [ ] **1.7** Simple JWT auth (register + login + protected routes)
- [ ] **1.8** Create `.env.example` and `docker-compose.yml` for local dev
- [ ] **1.9** Deploy skeleton to Railway

### Tests for This Phase

```python
# test_foundation.py
def test_health_check():              # GET /health returns 200
def test_db_connection():             # Can connect and query
def test_celery_task():               # Basic task enqueues and executes
def test_auth_register_login():       # Register → login → get JWT → access protected route
```

### Deliverable
Backend responds to health check. Frontend loads. Database migrated. Celery processes a test job. Auth works.

---

## Phase 2: Integration Connectors (Ingestion)

**Goal:** Ingest real events from Slack and GitHub into the events table.
**Estimated time:** 1 day (Day 1 afternoon + Day 2 morning)

### Tasks

- [ ] **2.1** Implement Slack OAuth flow (app install → store tokens)
- [ ] **2.2** Build Slack webhook receiver with signature verification
- [ ] **2.3** Parse Slack events (messages, reactions, file shares) → normalized Event objects
- [ ] **2.4** Implement GitHub App installation flow
- [ ] **2.5** Build GitHub webhook receiver with secret verification
- [ ] **2.6** Parse GitHub events (push, PRs, reviews, issue comments) → normalized Event objects
- [ ] **2.7** Build Celery task: `ingest_event` — normalize and store in events table
- [ ] **2.8** Build embedding generation for all ingested events (Gemini `text-embedding-004` via Backboard API)
- [ ] **2.9** Create integration settings API and basic settings UI page

### Tests for This Phase

```python
# test_webhooks.py
def test_slack_message_parsing():         # Raw Slack payload → Event object
def test_slack_reaction_parsing():        # Reaction payload → Event object
def test_github_push_parsing():           # Push payload → Event object
def test_github_pr_parsing():             # PR payload → Event object
def test_slack_signature_verification():  # Valid sig passes, invalid rejected
def test_github_secret_verification():    # Valid secret passes, invalid rejected

# test_ingestion.py
def test_event_stored_with_embedding():   # Event + embedding persisted to DB
def test_duplicate_event_ignored():       # Same source_id not double-stored
```

### Deliverable
Slack messages and GitHub events flow into the `events` table in real-time with embeddings.

---

## Phase 3: Knowledge Extraction Engine

**Goal:** Automatically identify and structure significant events.
**Estimated time:** Half day (Day 2 afternoon)

### Tasks

- [ ] **3.1** Implement pre-filter (regex/keyword matching for significance signals)
- [ ] **3.2** Build Backboard API LLM client (`app/backboard/llm.py` — chat, embeddings, function calling, model selection, error handling)
- [ ] **3.3** Implement classification prompt + response parsing
- [ ] **3.4** Implement extraction prompt + response parsing (including `expected_follow_ups`)
- [ ] **3.5** Create Celery task: `extract_knowledge` — pre-filter → classify → extract → store
- [ ] **3.6** Wire up: new events automatically trigger extraction pipeline
- [ ] **3.7** Create seed dataset: ~15 realistic Slack messages + GitHub events
- [ ] **3.8** Test and tune against seed dataset — aim for >70% precision

### Tests for This Phase (TDD — Critical)

```python
# test_detection.py
def test_prefilter_catches_decision_language():    # "We've decided to..." passes
def test_prefilter_rejects_casual_chat():           # "Hey want to grab lunch?" filtered
def test_prefilter_catches_approval_language():     # "Approved" passes
def test_prefilter_catches_change_language():       # "Updated the BOM" passes

def test_classification_parses_valid_json():        # LLM response → structured result
def test_classification_handles_malformed_json():   # Graceful failure on bad response

def test_extraction_parses_decision():              # LLM response → KO fields
def test_extraction_includes_expected_follow_ups(): # Follow-ups extracted for verification agent
def test_extraction_handles_missing_fields():       # Missing rationale → None, not crash

def test_pipeline_end_to_end():                     # Event in → KnowledgeObject out
def test_pipeline_filters_noise():                  # Casual message → no KO created
```

### Deliverable
When a significant message arrives from Slack or a meaningful PR is merged on GitHub, a Knowledge Object is automatically created with structured fields including expected follow-ups.

---

## Phase 4: Cross-Tool Correlation Engine

**Goal:** Merge related events from different sources into unified Knowledge Objects.
**Estimated time:** Half day (Day 3 morning)

### Tasks

- [ ] **4.1** Implement semantic similarity scoring (cosine distance on embeddings)
- [ ] **4.2** Implement actor overlap scoring
- [ ] **4.3** Implement temporal proximity scoring
- [ ] **4.4** Implement explicit reference detection (shared URLs, file names, ticket IDs)
- [ ] **4.5** Build weighted correlation scoring function
- [ ] **4.6** Implement Knowledge Object merge logic (combine participants, artifacts, regen summary)
- [ ] **4.7** Create Celery periodic task: run correlation every 2 minutes
- [ ] **4.8** Create demo scenario: Slack message + GitHub commit that should auto-merge

### Tests for This Phase (TDD — Critical)

```python
# test_correlation.py
def test_semantic_similarity_high_for_related():    # Same-topic events score > 0.75
def test_semantic_similarity_low_for_unrelated():   # Different topics score < 0.5
def test_actor_overlap_scoring():                   # Same actor → high score
def test_temporal_proximity_scoring():              # 1 hour apart → high; 20 hours → low
def test_reference_detection_finds_urls():          # Shared GitHub URL detected
def test_reference_detection_finds_filenames():     # Shared file name detected

def test_weighted_score_merges_above_threshold():   # Score > 0.6 → merge
def test_weighted_score_no_merge_below_threshold(): # Score < 0.6 → no merge

def test_merge_combines_participants():             # Union of participant lists
def test_merge_combines_events():                   # Union of linked events
def test_merge_keeps_higher_confidence():           # Primary = higher confidence KO
```

### Deliverable
A Slack message saying "switching to MotorCo" and a GitHub commit updating the BOM are automatically merged into a single Knowledge Object with both artifacts linked.

---

## Phase 5: Verification Agent

**Goal:** After Knowledge Objects are created, an agent verifies implementation across tools.
**Estimated time:** Half day (Day 3 afternoon)

### Tasks

- [ ] **5.1** Implement agent tool functions: `search_events_by_content`, `search_events_by_actor`, `record_verification_check`
- [ ] **5.2** Build verification agent system prompt and tool definitions
- [ ] **5.3** Implement agent execution loop with max iteration safeguard (10 iterations max)
- [ ] **5.4** Create Celery task: `run_verification` — dispatched after KO creation/merge
- [ ] **5.5** Wire up: KO creation → automatic verification dispatch
- [ ] **5.6** Build verification check storage and retrieval
- [ ] **5.7** Test with demo scenario: decision with BOM update (verified) + missing procurement ticket (flagged)

### Tests for This Phase (TDD — Critical)

```python
# test_verification_agent.py
def test_agent_tool_search_events_by_content():     # Tool returns relevant events
def test_agent_tool_search_events_by_actor():       # Tool returns actor's events
def test_agent_tool_record_check():                 # Check is persisted to DB

def test_agent_identifies_verified_action():        # BOM commit found → "verified"
def test_agent_identifies_missing_action():         # No procurement ticket → "missing" + suggestion
def test_agent_stops_at_max_iterations():           # Doesn't exceed 10 tool calls
def test_agent_handles_no_expected_follow_ups():    # KO with no follow-ups → minimal checks
```

### Deliverable
After "Switch to MotorCo" Knowledge Object is created, verification agent checks GitHub for BOM update (verified), checks for procurement ticket (missing), and suggests creating one.

---

## Phase 6: Investigative Chat Agent & Dashboard

**Goal:** Users can query project memory via agent-powered chat (primary) and browse knowledge objects with verification status (secondary).
**Estimated time:** 1 day (Day 3 evening + Day 4)

### Tasks

- [ ] **6.1** Implement query agent tools: `search_knowledge_base`, `search_raw_events`, `get_knowledge_detail`, `get_verification_status`
- [ ] **6.2** Build investigative agent system prompt and tool definitions
- [ ] **6.3** Implement streaming agent execution with SSE (agent steps + final answer)
- [ ] **6.4** Build Chat page UI — input, streaming agent steps, final answer, source citations
- [ ] **6.5** Build AgentStep component (shows tool call + result, collapsible)
- [ ] **6.6** Build ReasoningToggle (show/hide agent thinking)
- [ ] **6.7** Build knowledge feed API (`GET /api/knowledge` with pagination + filters + verification status)
- [ ] **6.8** Build Knowledge feed page — cards with type, title, confidence, verification status badge
- [ ] **6.9** Build Knowledge detail page — full view with artifacts, timeline, and verification panel
- [ ] **6.10** Build VerificationPanel component (list of checks: verified/missing/suggestion)
- [ ] **6.11** Implement confirm/dismiss actions on knowledge objects
- [ ] **6.12** Polish UI: loading states, empty states, responsive layout
- [ ] **6.13** End-to-end demo rehearsal: ingest → detect → correlate → verify → chat → browse

### Tests for This Phase

```python
# test_investigator_agent.py
def test_agent_searches_knowledge_base():           # First step is always KB search
def test_agent_digs_into_raw_events():              # Falls back to raw events when KB incomplete
def test_agent_includes_verification_status():      # Reports implementation status in answer
def test_agent_stops_at_max_iterations():           # Doesn't exceed 8 tool calls
def test_agent_says_unknown_when_no_data():          # "I don't have information about that"

# test_search.py
def test_vector_search_returns_relevant():          # Query about motors → motor decision
def test_vector_search_respects_project():          # Only returns results from same project
def test_context_formatting():                      # KOs formatted into clean context
```

### Deliverable
Complete hackathon demo. Agent-powered chat answers questions with multi-step reasoning and verification status. Dashboard shows Knowledge Objects with verification badges.

---

## Hackathon Demo Script (5 minutes)

1. **Problem (45 sec):** "Engineering teams make hundreds of decisions across Slack, GitHub, Drive — but none of it is connected. When someone asks 'why did we switch suppliers?' nobody can find the answer. And worse — nobody checks if the decision was actually implemented."

2. **Solution (30 sec):** "Sense automatically watches your tools, captures significant engineering moments, correlates events across platforms, verifies implementation, and makes it all queryable through an AI agent."

3. **Live demo — Connect (30 sec):** Show Slack and GitHub already connected in settings.

4. **Live demo — Trigger (1 min):** Send a Slack message: *"After testing both options, going with MotorCo as our primary supplier. Updating the BOM now."* Push a pre-prepared GitHub commit updating the BOM.

5. **Live demo — Watch it work (30 sec):** Show Sense automatically creating a Knowledge Object linking both events. Show the verification panel: BOM updated ✅, Procurement ticket ❌ Missing — "Consider creating a procurement ticket for MotorCo."

6. **Live demo — Query (1.5 min):** Open chat, ask: *"Why did we choose MotorCo?"* **Toggle agent reasoning ON** — watch it search the knowledge base, pull raw Slack context, check verification status. Final answer cites both sources and reports: "Decision is partially implemented — BOM updated, but no procurement ticket found."

7. **Differentiator (30 sec):** "Existing tools find documents. Sense creates structured knowledge, links events across tools, and verifies follow-through. No other tool does this for mid-size engineering teams."

8. **Vision (15 sec):** "Every engineering decision — captured, verified, and queryable. That's Sense, powered by Backboard."

---

## Day-by-Day Plan

| Day | Morning | Afternoon | Evening |
|---|---|---|---|
| **Day 1** | Phase 1: Foundation (backend, DB, Celery, frontend skeleton) | Phase 2: Slack + GitHub webhooks, event parsing | Phase 2: Embeddings, integration settings |
| **Day 2** | Phase 2: Finish connectors, test with real webhooks | Phase 3: Pre-filter + LLM classification + extraction | Phase 3: Wire up pipeline, seed data, tune |
| **Day 3** | Phase 4: Correlation engine (scoring + merge) | Phase 5: Verification agent (tools + execution + tests) | Phase 6: Chat agent backend + start UI |
| **Day 4** | Phase 6: Chat UI + dashboard + verification panel | Phase 6: Polish + end-to-end demo rehearsal | **Demo** |

---

## Post-Hackathon Roadmap

### Phase 7: Production Hardening

- [ ] Proper error handling and retry logic
- [ ] Rate limiting on API and webhook endpoints
- [ ] Structured logging and monitoring (Sentry)
- [ ] Database connection pooling and query optimization
- [ ] Credential encryption at rest (beyond Fernet)
- [ ] Input validation and sanitization
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Periodic re-verification (24/48/72 hour re-checks on unresolved KOs)

### Phase 8: Extended Integrations

- [ ] Google Drive connector (polling → push notifications)
- [ ] Microsoft Teams connector
- [ ] Email connector (Gmail API / Microsoft Graph)
- [ ] Jira connector
- [ ] Meeting transcript connector (Zoom, Google Meet, Teams)
- [ ] Browser extension (opt-in capture + inline queries)
- [ ] Confluence / Notion connector

### Phase 9: Advanced Features

- [ ] Knowledge Object versioning (superseded/reversed tracking)
- [ ] Conflict detection agent (identifies contradictory decisions across teams)
- [ ] Knowledge graph visualization (how decisions relate to each other)
- [ ] Team analytics (knowledge velocity, verification rates, follow-through gaps)
- [ ] Automated weekly digest with verification status summary
- [ ] Slack bot for inline queries (`@sense why did we choose MotorCo?`)
- [ ] Fine-tuned classification model (trained on confirmed KOs)
- [ ] Self-hosted deployment (Docker Compose / Helm)
- [ ] SSO / SAML for enterprise
- [ ] SOC 2 compliance
- [ ] Extract Backboard as standalone API platform

---

## Technical Debt & Known Shortcuts (MVP)

| Shortcut | What to fix later |
|---|---|
| No PII redaction | Add configurable PII detection and masking |
| Simple JWT auth | Move to proper auth provider (Clerk, Auth0) |
| No webhook retry/dedup | Implement idempotent processing with dedup keys |
| No Google Drive integration | Add in Phase 8 |
| No database backups | Set up automated backups |
| No CI/CD | Add GitHub Actions for tests, lint, deploy |
| Hardcoded correlation thresholds | Make configurable per team |
| Single-region deployment | Multi-region for latency and redundancy |
| No LLM budget cap | Add circuit breaker and spending limits |
| No periodic re-verification | Add in Phase 7 (only initial verification in MVP) |
| Agent responses not cached | Cache tool results for repeated queries |

---

## Build Priority Decision Tree

When running low on time, cut in this order (last item = first to cut):

1. **KEEP:** Knowledge extraction from Slack messages (core value)
2. **KEEP:** Investigative chat agent with reasoning toggle (the "wow" moment — primary UI)
3. **KEEP:** Verification agent (the key differentiator — "was it implemented?")
4. **KEEP:** GitHub integration (proves cross-tool correlation)
5. **KEEP:** Correlation engine (merges cross-tool events)
6. Cut if needed: Knowledge dashboard (can demo everything via chat)
7. Cut if needed: User authentication (use shared demo account)
8. Cut if needed: Integration setup UI (pre-configure via env vars)
9. Cut if needed: Confirm/dismiss actions (passive capture only)
10. Cut if needed: Agent reasoning toggle (just show results, explain reasoning verbally in demo)
