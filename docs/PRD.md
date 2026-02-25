# Sense — Product Requirements Document (Build Spec)

**Version:** 1.0
**Last Updated:** 2026-02-24
**Platform API:** Backboard.io (AI memory & retrieval)

> For pitch positioning, target users, competitive analysis, and demo talking points, see [PITCH_POSITIONING.md](./PITCH_POSITIONING.md).
> For data model, API design, project structure, and code examples, see [TECHNICAL_SPEC.md](./TECHNICAL_SPEC.md).
> For phase-by-phase task breakdown and day-by-day plan, see [ROADMAP.md](./ROADMAP.md).

---

## 1. Overview

Sense is a **cross-platform engineering memory with active verification**. It ingests events from Slack and GitHub via webhooks, automatically extracts structured Knowledge Objects (decisions, changes, approvals), correlates related events across tools, dispatches AI agents to verify implementation, and exposes everything through an investigative chat interface and a browsable dashboard.

Built as a monolith with two internal layers:
- **Backboard** (internal module `app/backboard/`): event storage, embedding generation, vector search, Knowledge Object CRUD, agent tool implementations, **LLM gateway client** (routes all LLM calls through external Backboard API)
- **Sense** (internal module `app/sense/`): integration connectors, NLP detection, correlation engine, verification agents, investigative query agents, user-facing API + frontend

All LLM calls (classification, extraction, agents, embeddings) go through the **Backboard API**, an external model-routing gateway that provides access to Gemini, GPT, and other providers.

---

## 2. Core Concepts

### 2.1 Knowledge Object

The atomic unit of Sense. A structured record representing a meaningful engineering event captured from cross-tool activity.

**Types:** `decision` | `change` | `approval` | `blocker` | `context`

```json
{
  "id": "ko_8f3a...",
  "type": "decision",
  "title": "Switch primary motor supplier to MotorCo",
  "summary": "Team decided to switch from SupplierA to MotorCo due to 30% cost reduction and better lead times.",
  "detail": {
    "statement": "We will use MotorCo as our primary motor supplier starting Q2.",
    "rationale": "MotorCo offers 30% lower unit cost, 2-week lead times vs 6-week, and passed qualification testing.",
    "alternatives_considered": [
      "Stay with SupplierA (rejected: cost too high)",
      "Dual-source between both (rejected: complexity not justified)"
    ],
    "expected_follow_ups": [
      "Update BOM in GitHub",
      "Upload qualification report to Drive",
      "Create procurement ticket"
    ]
  },
  "participants": ["alice@company.com", "bob@company.com"],
  "artifacts": [
    { "source": "slack", "type": "thread", "url": "...", "snippet": "..." },
    { "source": "github", "type": "commit", "url": "...", "message": "Update BOM with MotorCo parts" }
  ],
  "verification": {
    "status": "partial",
    "checks": [
      { "description": "BOM updated in GitHub", "status": "verified", "evidence": "commit abc123" },
      { "description": "Procurement ticket created", "status": "missing", "suggestion": "Create procurement ticket for MotorCo initial order" }
    ],
    "last_verified_at": "2026-02-21T10:00:00Z"
  },
  "timestamp": "2026-02-20T14:32:00Z",
  "confidence": 0.87,
  "status": "active",
  "tags": ["supply-chain", "motors", "cost-reduction"],
  "project": "proj_rover_v2"
}
```

### 2.2 Cross-Tool Event Correlation

When related events happen across tools (e.g., a Slack message + GitHub commit + file upload), Sense correlates them into a single Knowledge Object using weighted scoring:

| Signal | Weight | Description |
|---|---|---|
| Semantic similarity | 0.35 | Cosine similarity of embeddings > 0.75 threshold |
| Actor overlap | 0.25 | Same person or overlapping participant set |
| Temporal proximity | 0.20 | Events within configurable window (default: 4 hours) |
| Explicit references | 0.20 | Shared URLs, file names, @mentions, ticket IDs |

**Merge threshold:** Correlation score > 0.6

### 2.3 Verification Agents

After a Knowledge Object is created, a **verification agent** (Gemini 2.0 Flash via Backboard API, function calling) is dispatched that:

1. Reads the KO's `expected_follow_ups` and decision content
2. Searches connected tools for evidence of implementation using agent tools
3. Records verification checks: `verified` (with evidence) | `missing` (with suggestion) | `unknown`
4. Max **10 tool calls** per run (hard cap, prevents runaway)

**Agent tools:** `search_events_by_content`, `search_events_by_actor`, `record_verification_check`

**Constraints:**
- Agents do NOT evaluate whether decisions were "good" or "bad"
- Agents do NOT enforce process or block work
- Agents do NOT create tickets or take actions — they suggest, the human acts
- Only run on initial KO creation (no periodic re-verification in MVP)

### 2.4 Investigative Query Agents

When a user asks a question in chat, a **multi-step investigative agent** (Gemini 2.5 Pro via Backboard API, function calling) reasons through the question:

```
User: "Why did we switch motor suppliers?"

Agent reasoning:
  -> Step 1: search_knowledge_base("motor supplier switch") -> found KO
  -> Step 2: search_raw_events("motor supplier", source="slack") -> more context
  -> Step 3: get_verification_status(ko_id) -> implementation status
  -> Step 4: Synthesize answer with evidence chain and verification status
```

**Agent tools:** `search_knowledge_base`, `search_raw_events`, `get_knowledge_detail`, `get_verification_status`

**Max 8 tool calls** per query (hard cap).

### 2.5 User Interfaces

| Interface | Priority | Description |
|---|---|---|
| **Chat** | Primary | Natural language queries with streaming agent reasoning (toggleable visibility) |
| **Dashboard** | Secondary | Browsable feed of Knowledge Objects with verification status badges |

---

## 3. MVP Features (P0)

### 3.1 Cross-Tool Ingestion
- Real-time event capture from Slack + GitHub via webhooks
- Normalized event format regardless of source
- User-configurable monitoring scope (which channels, repos)
- Embedding generation for all ingested events (Gemini `text-embedding-004`, 768 dim)

### 3.2 Automatic Knowledge Extraction
- Pre-filter layer (regex/keyword) to minimize LLM API costs (~85% filtered out)
- LLM classification (Gemini 2.0 Flash): is this event significant? What type?
- LLM extraction (Gemini 2.0 Flash): structured Knowledge Object with `expected_follow_ups`
- Confidence scoring — high-confidence auto-captured, low-confidence flagged for review

### 3.3 Cross-Tool Correlation Engine
- Weighted scoring: semantic similarity, actor overlap, temporal proximity, explicit references
- Merge related KOs from different sources into unified records
- Entity resolution across tools (matching users across Slack, GitHub)
- Runs periodically (every 2 minutes via Celery)

### 3.4 Verification Agents
- Dispatched after KO creation/merge
- Infer expected follow-ups from decision content
- Search connected tools for implementation evidence
- Report status: `verified` / `missing` / `unknown`
- Suggest follow-up actions for gaps

### 3.5 Investigative Chat (Primary UI)
- Multi-step reasoning agents for answering user questions
- Streaming SSE responses with agent steps + final answer
- Toggleable reasoning visibility (show/hide agent thinking steps)
- Structured answers with evidence citations from multiple tools

### 3.6 Knowledge Dashboard (Secondary UI)
- Filterable feed of captured Knowledge Objects
- Verification status badges (verified / partial / missing)
- Detail view: full context, linked artifacts, verification checks, suggested actions
- Project-level grouping
- Confirm/dismiss actions for human feedback

### 3.7 Integration Connectors (MVP subset)

| Integration | MVP | Post-MVP |
|---|---|---|
| Slack | Yes | |
| GitHub | Yes | |
| Google Drive | | Yes (stretch) |
| Microsoft Teams | | Yes |
| Email (Gmail/O365) | | Yes |
| Jira | | Yes |
| Meeting Transcripts | | Yes |

### 3.8 User Controls (MVP-lite)
- Per-channel, per-repo opt-in monitoring
- Ability to redact or delete captured Knowledge Objects
- Simple JWT auth (register + login + protected routes)

---

## 4. User Flows

### 4.1 Onboarding
1. Sign up / login
2. Connect integrations (OAuth for Slack, GitHub)
3. Select which channels and repos to monitor
4. Sense begins processing live event streams

### 4.2 Passive Operation (Daily)
1. Team works normally — no behavior change required
2. Events are ingested via webhooks and processed asynchronously
3. Knowledge Objects accumulate automatically
4. Verification agents check implementation and flag gaps
5. Low-confidence items flagged for optional review

### 4.3 Querying (Primary Interaction)
1. User opens chat interface
2. Asks a question: "What did we decide about the battery thermal solution?"
3. Investigative agent searches knowledge base, raw events, and verification data
4. User sees agent reasoning steps (toggleable) and final answer with evidence
5. Answer includes verification status: "BOM updated. Manufacturing spec not yet updated."
6. Can follow up: "Who was involved? What alternatives did we consider?"

### 4.4 Reviewing Verification
1. User opens dashboard or sees flagged KO
2. Reviews what was done and what's missing
3. Sees suggested follow-up actions
4. Acts on suggestions (creates missing ticket, uploads missing doc, etc.)

### 4.5 Browsing Dashboard
1. User opens dashboard
2. Filters by project, date range, participant, knowledge type, or verification status
3. Reviews captured Knowledge Objects
4. Optionally confirms, edits, or dismisses entries

---

## 5. MVP Scope & Constraints

### In Scope (Hackathon)
1. Live ingestion from Slack + GitHub
2. Automatic extraction of Knowledge Objects from real events
3. Cross-tool correlation — KOs stitched from Slack message + GitHub commit
4. Verification agent — checks whether decisions were implemented
5. Investigative chat agent — multi-step reasoning with evidence and verification status
6. Dashboard — browsable feed with verification status badges

### Out of Scope (Hackathon)
- Google Drive, email, Teams, Jira, meeting transcripts
- Browser extension
- Advanced auth (SSO, SAML)
- Mobile
- Self-hosted deployment
- Backfill of historical data
- Periodic re-verification (only initial verification)
- PII redaction
- CI/CD pipeline

---

## 6. Build Priority (Cut Order)

When running low on time, cut in this order (last item = first to cut):

1. **KEEP:** Knowledge extraction from Slack messages (core value)
2. **KEEP:** Investigative chat agent with reasoning toggle (primary UI, the "wow" moment)
3. **KEEP:** Verification agent (key differentiator)
4. **KEEP:** GitHub integration (proves cross-tool correlation)
5. **KEEP:** Correlation engine (merges cross-tool events)
6. **Cut if needed:** Knowledge dashboard (can demo everything via chat)
7. **Cut if needed:** User authentication (use shared demo account)
8. **Cut if needed:** Integration setup UI (pre-configure via env vars)
9. **Cut if needed:** Confirm/dismiss actions (passive capture only)
10. **Cut if needed:** Agent reasoning toggle (show results, explain reasoning verbally)

---

## 7. Development Protocol

### TDD Workflow (Enforced)

For every feature:

```
1. Write test(s) for the feature
2. Run tests -> expect FAIL (confirms test is valid)
3. Implement the feature
4. Run tests -> check result
   +-- PASS -> mark feature done, move to next feature
   +-- FAIL -> fix the implementation (max 3 attempts)
                +-- PASS -> done
                +-- FAIL after 3 attempts -> STOP. Log to BLOCKED.md. Move on.
```

### Rules
| Rule | Detail |
|---|---|
| Max 3 fix attempts per failing test | After 3 consecutive failures on the same test, stop trying. |
| Each attempt must change something | Identical code counts as a wasted attempt. |
| Blocked features are logged | Append to `BLOCKED.md`: feature name, test file, failure output, what was tried. |
| Move on after blocking | Don't let one stubborn test stall the entire build. |
| Tests must be independent | A blocked feature should not prevent other features from being tested. |

### What Gets Tested (Hackathon Scope)

| Must Test (TDD) | Test After (Verification) | Skip Testing |
|---|---|---|
| Detection pipeline (pre-filter, classification parsing, extraction parsing) | Webhook payload parsing | Frontend components |
| Correlation scoring functions | API endpoint responses | CSS/styling |
| Agent tool functions (search, verification) | Database migrations | Auth flow |
| Agent loop safeguards (max iterations) | | Integration OAuth |
| Merge logic | | |

### Test Tooling
- **Framework:** pytest + pytest-asyncio
- **LLM mocking:** Record real LLM responses once, replay in tests (no live API calls in tests)
- **DB:** Separate test database with fixtures via conftest.py
- **Run command:** `pytest tests/ -v --tb=short`

---

## 8. Architecture Reference

See [TECHNICAL_SPEC.md](./TECHNICAL_SPEC.md) for:
- Architecture diagram and design principles
- Full tech stack with rationale
- Complete data model (SQL schemas + indexes)
- Ingestion layer details (Slack + GitHub webhook handling)
- Knowledge extraction pipeline (pre-filter, LLM classification, LLM extraction prompts)
- Correlation algorithm (full Python pseudocode)
- Verification agent (tools, system prompt, execution loop)
- Investigative query agent (tools, system prompt, streaming SSE)
- REST API endpoint list
- Frontend architecture (pages, components, hooks)
- Security considerations
- Project directory structure

---

## 9. Build Phases Reference

See [ROADMAP.md](./ROADMAP.md) for:
- Phase 1: Foundation & Infrastructure (backend, DB, Celery, frontend skeleton)
- Phase 2: Integration Connectors (Slack + GitHub webhooks, event parsing, embeddings)
- Phase 3: Knowledge Extraction Engine (pre-filter, LLM classification, LLM extraction)
- Phase 4: Cross-Tool Correlation Engine (scoring, merge logic)
- Phase 5: Verification Agent (tools, execution loop, auto-dispatch)
- Phase 6: Investigative Chat Agent & Dashboard (chat UI, dashboard, polish)
- Day-by-day schedule
- Post-hackathon roadmap (Phases 7-9)
- Technical debt & known shortcuts
