# Sense — Technical Specification

**Version:** 0.3
**Last Updated:** 2026-02-24
**Platform API:** Backboard.io

---

## 1. Architecture Overview

Sense follows an **event-driven pipeline architecture** with agents, and a clean internal separation between the Backboard memory/retrieval layer and the Sense application layer.

```
                        ┌───────────────────────────────────────────────────┐
                        │                  SENSE (Application)               │
                        │                                                   │
  ┌──────────┐          │  ┌────────────┐    ┌──────────────┐               │
  │  Slack    │──webhook─▶│  Ingestion  │───▶│  Detection &  │              │
  │  GitHub   │──webhook─▶│  Layer      │    │  Correlation  │              │
  └──────────┘          │  └────────────┘    └──────┬───────┘              │
                        │                           │                      │
                        │                    ┌──────▼───────┐              │
                        │                    │ Verification  │              │
                        │                    │ Agent         │              │
                        │                    └──────┬───────┘              │
                        │                           │                      │
                        ├───────────────────────────┼──────────────────────┤
                        │         BACKBOARD (Memory/Retrieval API)          │
                        │                           │                      │
                        │  ┌────────────┐    ┌──────▼───────┐    ┌────────┐│   ┌──────────────┐
                        │  │  Embedding  │    │  Knowledge   │    │ Agent  ││   │  Chat UI     │
                        │  │  Service    │    │  Object Store│    │ Tools  ││◀──│  (Primary)   │
                        │  └────────────┘    └──────────────┘    └────────┘│   └──────────────┘
                        │                                                   │
                        └───────────────────────────────────────────────────┘
```

### Internal Boundary: Backboard API Layer

The Backboard layer handles memory and retrieval concerns:
- Event and Knowledge Object storage (PostgreSQL + pgvector)
- Embedding generation and vector search
- Agent tool functions (search_knowledge, search_events, get_verification)
- CRUD operations on knowledge objects

The Sense layer handles application-specific logic:
- Integration connectors (Slack, GitHub webhooks)
- NLP detection and extraction (LLM calls)
- Cross-tool event correlation
- Verification agents (post-capture implementation checking)
- Investigative query agents (multi-step chat reasoning)
- User-facing API endpoints and frontend

**For the hackathon, these are one deployable monolith.** The boundary is a Python module/package separation, not a network boundary. Post-hackathon, the Backboard layer can be extracted into a standalone API.

### Design Principles (Hackathon-Scoped)

- **Monolith-first:** Single deployable backend. No microservices for MVP.
- **Async pipeline:** Event processing is decoupled from ingestion using a task queue.
- **LLM-light:** Use the cheapest viable model for each task. Pre-filter aggressively.
- **Webhook-first:** Prefer real-time webhooks over polling for integrations.
- **Chat-first UI:** The chat interface is the primary product surface. Dashboard is secondary.
- **Agent-powered:** Use Gemini function calling (via Backboard API) for both verification and query answering.

---

## 2. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | Python 3.12 + FastAPI | Fast to build, strong NLP/ML ecosystem, async-native |
| **Task Queue** | Celery + Redis | Decouples ingestion from processing; Redis doubles as cache |
| **Database** | PostgreSQL 16 + pgvector | Relational for structured data, pgvector for embedding search |
| **LLM Gateway** | **Backboard API** (external model router) | Abstracts provider SDKs; routes to Gemini, GPT, etc. |
| **LLM (Detection/Extraction)** | Gemini 2.0 Flash (via Backboard API) | Fast, cheap, good at classification/extraction |
| **LLM (Verification Agent)** | Gemini 2.0 Flash (via Backboard API) | Function calling capable, cost-effective for verification |
| **LLM (Chat/Investigative Agent)** | Gemini 2.5 Pro (via Backboard API) | Strong reasoning, function calling for multi-step investigation |
| **Embeddings** | Gemini `text-embedding-004` (via Backboard API) | 768 dimensions, free tier available |
| **Agent Framework** | Gemini function calling (native) | No extra framework; model handles tool selection and chaining |
| **Frontend** | React 19 + Vite + TailwindCSS | Fast to prototype, component-rich ecosystem |
| **Chat UI** | Custom agent interface (streaming) | FastAPI SSE endpoint + React chat component with reasoning toggle |
| **Deployment (MVP)** | Railway | One-click deploy, managed Postgres + Redis, cheap |
| **Auth (MVP)** | Simple JWT | Minimal auth for hackathon demo |

### Cost Estimates (Hackathon / Demo Scale)

| Resource | Estimated Cost |
|---|---|
| Gemini 2.0 Flash (classification + verification, ~5k events + ~100 agent runs) | ~$1–3 total (free tier may cover it) |
| Gemini 2.5 Pro (investigative chat agent, ~100 agent runs) | ~$3–8 total |
| Gemini Embeddings (~10k embeddings) | Free tier |
| Backboard API | Depends on plan |
| Railway hosting (4 days) | Free tier or ~$2 |
| PostgreSQL (managed) | Free tier |
| Redis (managed) | Free tier |
| **Total for hackathon** | **< $15** |

---

## 3. Data Model

### 3.1 Core Tables

```sql
-- Raw events from integrations (Backboard layer)
CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(50) NOT NULL,         -- 'slack', 'github', 'gdrive'
    source_id       VARCHAR(255) NOT NULL,         -- external ID from source system
    event_type      VARCHAR(100) NOT NULL,          -- 'message', 'commit', 'file_upload', etc.
    actor_email     VARCHAR(255),
    actor_name      VARCHAR(255),
    content         TEXT,                           -- message text, commit message, file name
    metadata        JSONB,                          -- source-specific fields
    raw_payload     JSONB,                          -- full webhook payload
    embedding       vector(768),                   -- Gemini text-embedding-004 dimension
    occurred_at     TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    project_id      UUID REFERENCES projects(id),
    UNIQUE(source, source_id)
);

-- Knowledge objects — decisions, changes, approvals, etc. (Backboard layer)
CREATE TABLE knowledge_objects (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type                VARCHAR(50) NOT NULL DEFAULT 'decision',  -- decision, change, approval, context
    title               VARCHAR(500) NOT NULL,
    summary             TEXT,
    detail              JSONB,                      -- type-specific structured data
    participants        JSONB,                      -- [{email, name, role}]
    tags                TEXT[],
    confidence          FLOAT NOT NULL DEFAULT 0.0,
    status              VARCHAR(50) DEFAULT 'active',  -- active, superseded, reversed, draft
    embedding           vector(768),
    detected_at         TIMESTAMPTZ DEFAULT NOW(),
    occurred_at         TIMESTAMPTZ,                -- when the event actually happened
    project_id          UUID REFERENCES projects(id),
    reviewed            BOOLEAN DEFAULT FALSE,
    reviewed_by         VARCHAR(255),
    reviewed_at         TIMESTAMPTZ
);

-- Links between knowledge objects and source events (Backboard layer)
CREATE TABLE knowledge_events (
    knowledge_id    UUID REFERENCES knowledge_objects(id) ON DELETE CASCADE,
    event_id        UUID REFERENCES events(id) ON DELETE CASCADE,
    relevance       FLOAT DEFAULT 1.0,
    relationship    VARCHAR(100),                    -- 'trigger', 'context', 'artifact', 'confirmation'
    PRIMARY KEY (knowledge_id, event_id)
);

-- Verification checks for knowledge objects (Sense layer)
CREATE TABLE verification_checks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_id    UUID REFERENCES knowledge_objects(id) ON DELETE CASCADE,
    description     TEXT NOT NULL,                   -- "BOM updated in GitHub"
    status          VARCHAR(50) NOT NULL,            -- 'verified', 'missing', 'unknown'
    evidence        TEXT,                            -- description of evidence found (commit hash, file name, etc.)
    suggestion      TEXT,                            -- suggested action if missing
    event_id        UUID REFERENCES events(id),     -- linked evidence event (if found)
    checked_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Merge audit trail
CREATE TABLE knowledge_merges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    primary_id      UUID REFERENCES knowledge_objects(id),
    merged_id       UUID,                           -- ID of the absorbed KO (now deleted)
    merge_score     FLOAT,
    merged_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Projects / workspaces
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    team_id         UUID REFERENCES teams(id)
);

-- Teams
CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Integration connections (Sense layer)
CREATE TABLE integrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id         UUID REFERENCES teams(id),
    source          VARCHAR(50) NOT NULL,
    credentials     JSONB,                           -- encrypted OAuth tokens
    config          JSONB,                           -- monitored channels, repos, folders
    status          VARCHAR(50) DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255),
    team_id         UUID REFERENCES teams(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Chat history
CREATE TABLE chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    project_id      UUID REFERENCES projects(id),
    role            VARCHAR(20) NOT NULL,            -- 'user', 'assistant', 'agent_step'
    content         TEXT NOT NULL,
    agent_reasoning JSONB,                           -- agent tool calls and reasoning steps (if role=assistant)
    sources         JSONB,                           -- referenced knowledge object IDs
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 Indexes

```sql
CREATE INDEX idx_events_source_time ON events (source, occurred_at);
CREATE INDEX idx_events_actor ON events (actor_email, occurred_at);
CREATE INDEX idx_events_project ON events (project_id, occurred_at);
CREATE INDEX idx_events_embedding ON events USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_ko_project ON knowledge_objects (project_id, detected_at);
CREATE INDEX idx_ko_type_status ON knowledge_objects (type, status, confidence);
CREATE INDEX idx_ko_embedding ON knowledge_objects USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_ko_tags ON knowledge_objects USING gin (tags);
CREATE INDEX idx_ko_occurred ON knowledge_objects (occurred_at);

CREATE INDEX idx_verification_ko ON verification_checks (knowledge_id, status);
```

---

## 4. Ingestion Layer (Sense)

### 4.1 Slack Integration

**Method:** Slack Events API (webhook-based)

**Monitored Events:**
- `message` — messages in monitored channels
- `message_changed` — edits to messages
- `reaction_added` — emoji reactions (approval signals like :white_check_mark:)
- `file_shared` — file uploads in channels

**Setup Flow:**
1. User installs Sense Slack app via OAuth
2. Selects which channels to monitor
3. Sense registers for events on those channels

**Processing:**
```python
@router.post("/webhooks/slack")
async def slack_webhook(request: Request):
    payload = await verify_slack_signature(request)

    # Handle Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event", {})

    # Enqueue for async processing
    process_event.delay(
        source="slack",
        source_id=event.get("ts"),
        event_type=event.get("type"),
        actor_email=await resolve_slack_user(event.get("user")),
        content=event.get("text", ""),
        metadata={
            "channel": event.get("channel"),
            "thread_ts": event.get("thread_ts"),
        },
        raw_payload=payload,
        occurred_at=float(event.get("ts", 0))
    )
    return {"ok": True}
```

### 4.2 GitHub Integration

**Method:** GitHub Webhooks + GitHub App

**Monitored Events:**
- `push` — commits pushed to monitored repos
- `pull_request` — PR opened, merged, closed
- `pull_request_review` — code review comments and approvals
- `issue_comment` — comments on issues/PRs

**Setup Flow:**
1. User installs Sense GitHub App
2. Selects which repos to monitor
3. GitHub sends webhooks for configured events

### 4.3 Google Drive Integration (Stretch Goal)

**Method:** Google Drive API + polling (every 5 minutes)

**Monitored Events:**
- File created in monitored folders
- File modified (version change)
- Comments added to documents

**MVP simplification:** Polling instead of push notifications. Only include if time allows.

---

## 5. Knowledge Extraction Engine (Sense)

### 5.1 Pipeline

```
Event ──▶ Embed ──▶ Pre-filter ──▶ LLM Classification ──▶ LLM Extraction ──▶ Knowledge Object ──▶ Verification Agent
                                        │
                                   (85% filtered out)
```

**Every event gets embedded** (for correlation and RAG search). Only events passing the pre-filter get sent to the LLM for classification. After a Knowledge Object is created, a verification agent is dispatched.

### 5.2 Pre-filter (Rule-Based, No LLM Cost)

Fast regex/keyword filter to reduce LLM API spend.

```python
SIGNIFICANCE_SIGNALS = [
    # Decision language
    r"we('ve| have)? decided", r"going (with|forward with)",
    r"final (call|decision|answer)", r"let's go with",
    r"we('re| are) (switching|moving|changing) to",

    # Approval language
    r"approved", r"sign(ed)? off", r"lgtm", r"green.?light",

    # Rejection language
    r"ruling out", r"we('re| are) not going (with|to)", r"rejected",

    # Change language
    r"updated", r"changed .+ to", r"new version", r"replaced",

    # Evaluation language
    r"after (comparing|evaluating|testing|reviewing)",
    r"pros and cons", r"trade.?off",
]
```

Also pass through: PR merges, emoji reactions with approval semantics, labeled issues.

**Expected filter rate:** ~85% of events filtered out before LLM.

### 5.3 LLM Classification (Gemini 2.0 Flash via Backboard API)

```
System: You classify engineering team events by significance.
Given an event from a collaboration tool, determine if it represents
a significant engineering moment (decision, change, approval, blocker).

Respond with JSON:
{
  "is_significant": true/false,
  "confidence": 0.0-1.0,
  "type": "decision|change|approval|blocker|context|none",
  "brief_reason": "why"
}

Event source: {source}
Event type: {event_type}
Author: {actor_name}
Content: {content}
```

### 5.4 LLM Extraction (Gemini 2.0 Flash via Backboard API)

For events classified as significant (confidence > 0.5):

```
System: Extract structured knowledge from this engineering team event.
Be precise — only include information explicitly stated or strongly implied.

Event source: {source}
Content: {content}
Context: {surrounding_messages_if_available}

Extract as JSON:
{
  "title": "short descriptive title",
  "summary": "1-2 sentence summary",
  "type": "decision|change|approval|blocker",
  "detail": {
    "statement": "the specific decision/change/approval",
    "rationale": "why (if stated)",
    "alternatives_considered": ["if any mentioned"],
    "expected_follow_ups": ["what actions should follow from this"]
  },
  "tags": ["relevant topic tags"]
}
```

Note: `expected_follow_ups` is extracted here and used by the verification agent.

---

## 6. Cross-Tool Correlation Engine (Sense)

### 6.1 Correlation Signals (Weighted)

| Signal | Weight | Description |
|---|---|---|
| Semantic similarity | 0.35 | Cosine similarity of embeddings > 0.75 threshold |
| Actor overlap | 0.25 | Same person or overlapping participant set |
| Temporal proximity | 0.20 | Events within configurable window (default: 4 hours) |
| Explicit references | 0.20 | Shared URLs, file names, @mentions, ticket IDs |

**Merge threshold:** Correlation score > 0.6

### 6.2 Algorithm

```python
async def correlate_new_knowledge(ko: KnowledgeObject, window_hours: int = 24):
    """Attempt to merge a new KO with existing recent ones."""

    candidates = await backboard.get_recent_knowledge(
        project_id=ko.project_id,
        since=ko.occurred_at - timedelta(hours=window_hours),
        exclude_id=ko.id
    )

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        score = 0.0

        # Semantic similarity (highest weight — most reliable signal)
        sim = cosine_similarity(ko.embedding, candidate.embedding)
        if sim > 0.75:
            score += 0.35 * sim

        # Actor overlap
        ko_actors = {p["email"] for p in ko.participants}
        cand_actors = {p["email"] for p in candidate.participants}
        if ko_actors & cand_actors:
            score += 0.25 * (len(ko_actors & cand_actors) / len(ko_actors | cand_actors))

        # Temporal proximity
        time_diff = abs((ko.occurred_at - candidate.occurred_at).total_seconds())
        score += 0.20 * max(0, 1 - (time_diff / (window_hours * 3600)))

        # Explicit references
        shared_refs = find_shared_references(ko, candidate)
        if shared_refs:
            score += 0.20 * min(1.0, len(shared_refs) / 3)

        if score > best_score:
            best_score = score
            best_match = candidate

    if best_match and best_score > 0.6:
        await merge_knowledge_objects(best_match, ko)

    return best_match, best_score
```

### 6.3 Merge Strategy

1. Keep the **higher-confidence** object as primary
2. Merge participants (union)
3. Merge linked events (union)
4. Use LLM to regenerate a unified summary from combined context
5. Record the merge in `knowledge_merges` audit table
6. Re-trigger verification agent on the merged object

---

## 7. Verification Agent (Sense)

### 7.1 Overview

After a Knowledge Object is created (or merged), a **verification agent** is dispatched as a Celery task. The agent uses Gemini 2.0 Flash with function calling (via Backboard API) to check whether expected follow-up actions have been implemented across connected tools.

### 7.2 Agent Tools

The verification agent has access to these tools via Gemini function calling:

```python
VERIFICATION_TOOLS = [
    {
        "name": "search_events_by_content",
        "description": "Search ingested events for content matching a query. "
                       "Use this to find commits, file uploads, or messages related to an expected action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Semantic search query"},
                "source": {"type": "string", "enum": ["slack", "github", "gdrive", "any"]},
                "since_hours": {"type": "integer", "description": "Only search events from the last N hours"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_events_by_actor",
        "description": "Search events by a specific actor (email). "
                       "Use this to check if a person followed through on their stated action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "actor_email": {"type": "string"},
                "source": {"type": "string", "enum": ["slack", "github", "gdrive", "any"]},
                "since_hours": {"type": "integer"}
            },
            "required": ["actor_email"]
        }
    },
    {
        "name": "record_verification_check",
        "description": "Record a verification check result for the knowledge object.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What was being checked"},
                "status": {"type": "string", "enum": ["verified", "missing", "unknown"]},
                "evidence": {"type": "string", "description": "Evidence found (or null)"},
                "suggestion": {"type": "string", "description": "Suggested follow-up action (if missing)"},
                "event_id": {"type": "string", "description": "UUID of the evidence event (if found)"}
            },
            "required": ["description", "status"]
        }
    }
]
```

### 7.3 Agent System Prompt

```
You are a verification agent for Sense, an engineering project memory system.

You have been given a Knowledge Object (a captured engineering decision, change, or approval).
Your job is to verify whether the expected follow-up actions have been implemented across
the team's connected tools (Slack, GitHub, Google Drive).

Instructions:
1. Read the knowledge object carefully. Identify what follow-up actions should have happened.
2. Use the search tools to look for evidence of each expected action.
3. For each expected action, record a verification check:
   - "verified" if you found clear evidence it was done
   - "missing" if you searched and couldn't find evidence
   - "unknown" if you can't determine (insufficient data)
4. For missing actions, suggest a specific follow-up action.
5. Be conservative — only mark "verified" if the evidence is clear. Prefer "unknown" over false positives.
6. Do NOT evaluate whether the decision was good or bad. Only check implementation.

Knowledge Object:
{knowledge_object_json}
```

### 7.4 Agent Execution

```python
async def run_verification_agent(ko: KnowledgeObject):
    """Run verification agent on a knowledge object."""
    from app.backboard.llm import backboard_llm  # Backboard API client

    # Build tool implementations
    tool_handlers = {
        "search_events_by_content": lambda params: backboard.vector_search_events(
            query=params["query"],
            source=params.get("source", "any"),
            since_hours=params.get("since_hours", 72),
            project_id=ko.project_id
        ),
        "search_events_by_actor": lambda params: backboard.search_events_by_actor(
            actor_email=params["actor_email"],
            source=params.get("source", "any"),
            since_hours=params.get("since_hours", 72),
            project_id=ko.project_id
        ),
        "record_verification_check": lambda params: store_verification_check(
            knowledge_id=ko.id,
            **params
        ),
    }

    # Run agent loop (max 10 tool calls to prevent runaway)
    messages = [{"role": "user", "content": VERIFICATION_PROMPT.format(
        knowledge_object_json=ko.to_json()
    )}]

    for _ in range(10):  # Max iterations safeguard
        response = await backboard_llm.chat(
            model="gemini-2.0-flash",
            system=VERIFICATION_SYSTEM_PROMPT,
            messages=messages,
            tools=VERIFICATION_TOOLS,
            max_tokens=2048,
        )

        # Process function calls
        if response.has_function_calls:
            tool_results = []
            for call in response.function_calls:
                result = await tool_handlers[call.name](call.args)
                tool_results.append({
                    "function_call_id": call.id,
                    "name": call.name,
                    "result": json.dumps(result)
                })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "tool", "content": tool_results})
        else:
            break  # Agent is done

    return await get_verification_checks(ko.id)
```

> **Note:** The exact request/response format depends on the Backboard API spec. The pattern above is pseudocode — adapt to the actual Backboard API client interface. The key logic (tool dispatch loop, max iterations, tool handlers) stays the same regardless of SDK.

---

## 8. Investigative Query Agent (Sense)

### 8.1 Overview

When a user asks a question in the chat interface, instead of single-hop RAG, Sense dispatches an **investigative agent** that can reason through the question in multiple steps.

### 8.2 Agent Tools

```python
QUERY_AGENT_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the structured knowledge base for decisions, changes, and approvals. "
                       "Returns knowledge objects with summaries, participants, and linked artifacts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "type_filter": {"type": "string", "enum": ["decision", "change", "approval", "blocker", "any"]},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_raw_events",
        "description": "Search raw ingested events (Slack messages, GitHub commits, file uploads). "
                       "Use this when the knowledge base doesn't have enough context and you need "
                       "to dig into the original source material.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {"type": "string", "enum": ["slack", "github", "gdrive", "any"]},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_knowledge_detail",
        "description": "Get full details of a specific knowledge object including all linked events, "
                       "artifacts, and verification status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "knowledge_id": {"type": "string"}
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "get_verification_status",
        "description": "Get the verification status of a knowledge object — what follow-up actions "
                       "were verified, what's missing, and what's suggested.",
        "input_schema": {
            "type": "object",
            "properties": {
                "knowledge_id": {"type": "string"}
            },
            "required": ["knowledge_id"]
        }
    }
]
```

### 8.3 Agent System Prompt

```
You are Sense, an investigative engineering memory assistant.

When a user asks a question about their project history, you have tools to investigate:
1. Search the structured knowledge base (decisions, changes, approvals)
2. Search raw events (Slack messages, GitHub commits, file uploads)
3. Get full details and verification status of specific knowledge objects

Investigation approach:
- Start with the knowledge base. If the answer is clear, respond.
- If the knowledge base is incomplete, search raw events for more context.
- If you find a relevant knowledge object, check its verification status to report
  on implementation follow-through.
- Always cite your sources with [KO:id] for knowledge objects and [Event:id] for raw events.
- If you can't find the answer, say so clearly.
- Never fabricate information. Only report what the evidence shows.
```

### 8.4 Streaming Agent Responses

The chat endpoint streams both agent reasoning steps and the final answer:

```python
@router.post("/api/chat")
async def chat_query(query: ChatQuery, current_user: User = Depends(get_current_user)):
    """Stream agent investigation + answer."""
    from app.backboard.llm import backboard_llm  # Backboard API client

    async def generate():
        messages = [{"role": "user", "content": query.question}]

        for iteration in range(8):  # Max 8 function-calling rounds
            response = await backboard_llm.chat_stream(
                model="gemini-2.5-pro",
                system=QUERY_AGENT_SYSTEM_PROMPT,
                messages=messages,
                tools=QUERY_AGENT_TOOLS,
                max_tokens=4096,
            )

            async for event in response:
                if event.type == "function_call_start":
                    # Stream agent reasoning step to frontend
                    yield json.dumps({
                        "type": "agent_step",
                        "tool": event.function_name,
                        "status": "searching"
                    }) + "\n"

                elif event.type == "text_delta":
                    # Stream final text answer
                    yield json.dumps({
                        "type": "text",
                        "content": event.text
                    }) + "\n"

            # Handle function calls
            if response.has_function_calls:
                tool_results = await execute_tool_calls(response, query.project_id)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "tool", "content": tool_results})

                # Stream tool results to frontend
                for result in tool_results:
                    yield json.dumps({
                        "type": "agent_step",
                        "tool": result["tool_name"],
                        "status": "complete",
                        "result_preview": result.get("preview", "")
                    }) + "\n"
            else:
                break  # Agent finished

    return StreamingResponse(generate(), media_type="text/event-stream")
```

> **Note:** The streaming event format depends on the Backboard API. The pattern above is pseudocode — adapt to the actual Backboard API streaming interface. The key logic (SSE format, agent step streaming, tool dispatch loop) stays the same.

---

## 9. API Design

### 9.1 REST Endpoints

```
# Auth
POST   /api/auth/login
POST   /api/auth/register

# Integrations (Sense layer)
GET    /api/integrations
POST   /api/integrations/{source}/connect    # Start OAuth flow
POST   /api/integrations/{source}/callback   # OAuth callback
DELETE /api/integrations/{id}
PATCH  /api/integrations/{id}/config

# Knowledge Objects (Backboard layer, exposed via Sense API)
GET    /api/knowledge                        # List (paginated, filterable by type/project/date/tag/verification_status)
GET    /api/knowledge/{id}                   # Detail with linked events, artifacts, and verification checks
PATCH  /api/knowledge/{id}                   # Edit (title, status, tags)
DELETE /api/knowledge/{id}
POST   /api/knowledge/{id}/confirm           # Human confirms accuracy
POST   /api/knowledge/{id}/dismiss           # Human dismisses false positive
GET    /api/knowledge/{id}/verification      # Get verification checks for a KO

# Chat (Agent-powered, exposed via Sense API)
POST   /api/chat                             # Query project memory (streaming SSE with agent steps)
GET    /api/chat/history                     # Chat history for current project

# Events (debug/admin)
GET    /api/events

# Projects
GET    /api/projects
POST   /api/projects

# Webhooks (called by external services)
POST   /webhooks/slack
POST   /webhooks/github
```

---

## 10. Frontend Architecture

### 10.1 Pages (Chat-First)

| Page | Priority | Description |
|---|---|---|
| `/chat` | **Primary** | Chat interface with agent reasoning toggle |
| `/knowledge` | Secondary | Knowledge feed with verification status badges |
| `/knowledge/:id` | Secondary | Detail view with artifacts, timeline, and verification checks |
| `/settings` | Setup | Connect integrations, configure monitoring |
| `/login` | Auth | Simple JWT login |

### 10.2 Key Components

```
frontend/src/
├── components/
│   ├── chat/
│   │   ├── ChatInterface.tsx       # Main chat UI with streaming responses
│   │   ├── ChatMessage.tsx         # Message bubble with citation links
│   │   ├── AgentStep.tsx           # Reasoning step display (tool call + result)
│   │   ├── ReasoningToggle.tsx     # Show/hide agent thinking steps
│   │   ├── SourceCard.tsx          # Inline source preview (Slack/GitHub/Drive)
│   │   └── ChatInput.tsx           # Message input with project selector
│   ├── knowledge/
│   │   ├── KnowledgeCard.tsx       # Card with type, title, confidence, verification status
│   │   ├── KnowledgeDetail.tsx     # Full view with artifacts and timeline
│   │   ├── VerificationPanel.tsx   # Verification checks list (verified/missing/suggestion)
│   │   ├── ArtifactLink.tsx        # Clickable link to source tool
│   │   ├── ConfidenceBadge.tsx     # Visual confidence indicator
│   │   └── FilterBar.tsx           # Filters by type, project, date, tag, verification status
│   └── settings/
│       └── IntegrationSetup.tsx    # OAuth connection flow
├── pages/
│   ├── ChatPage.tsx
│   ├── KnowledgePage.tsx
│   ├── KnowledgeDetailPage.tsx
│   ├── SettingsPage.tsx
│   └── LoginPage.tsx
├── hooks/
│   ├── useChat.ts                  # Chat state + SSE streaming + agent step tracking
│   ├── useKnowledge.ts             # Knowledge CRUD + pagination
│   └── useIntegrations.ts          # Integration connection state
└── lib/
    ├── api.ts                      # API client (fetch wrapper)
    └── types.ts                    # TypeScript types
```

---

## 11. Security Considerations (MVP)

| Concern | MVP Approach |
|---|---|
| OAuth tokens | Stored encrypted in DB (Fernet symmetric encryption) |
| API authentication | JWT tokens with short expiry |
| Webhook verification | Verify Slack signing secret, GitHub webhook secret |
| Data access | Team-scoped — users only see their team's data |
| LLM data exposure | Only send content to LLM, never credentials or tokens |
| Agent tool access | Agents can only search data within the user's team scope |
| PII | No automated redaction in MVP (post-MVP feature) |

---

## 12. Project Structure

```
backboard/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, startup, middleware
│   │   ├── config.py               # Settings from environment
│   │   ├── database.py             # DB connection, session management
│   │   │
│   │   ├── backboard/              # ── Backboard memory/retrieval layer ──
│   │   │   ├── __init__.py
│   │   │   ├── llm.py              # Backboard API client (LLM gateway: chat, embeddings, function calling)
│   │   │   ├── models.py           # SQLAlchemy models (events, knowledge_objects, verification_checks)
│   │   │   ├── store.py            # CRUD operations for knowledge objects and events
│   │   │   ├── embeddings.py       # Embedding generation (Gemini via Backboard API)
│   │   │   ├── search.py           # Vector search and retrieval
│   │   │   └── tools.py            # Agent tool implementations (search_knowledge, search_events, etc.)
│   │   │
│   │   ├── sense/                  # ── Sense application layer ──
│   │   │   ├── __init__.py
│   │   │   ├── detection.py        # Knowledge extraction pipeline (pre-filter + LLM)
│   │   │   ├── correlation.py      # Cross-tool correlation engine
│   │   │   ├── agents/
│   │   │   │   ├── verification.py # Verification agent (post-capture implementation check)
│   │   │   │   └── investigator.py # Investigative query agent (chat)
│   │   │   ├── integrations/       # Integration connectors
│   │   │   │   ├── slack.py
│   │   │   │   └── github.py
│   │   │   └── tasks.py            # Celery tasks (process_event, correlate, verify)
│   │   │
│   │   ├── api/                    # ── API routers ──
│   │   │   ├── auth.py
│   │   │   ├── knowledge.py
│   │   │   ├── chat.py
│   │   │   ├── integrations.py
│   │   │   └── webhooks.py
│   │   │
│   │   └── models/                 # ── Shared SQLAlchemy models ──
│   │       ├── user.py
│   │       ├── team.py
│   │       ├── project.py
│   │       └── integration.py
│   │
│   ├── alembic/                    # Database migrations
│   ├── tests/                      # Test suite (see Section 13)
│   │   ├── conftest.py
│   │   ├── test_detection.py
│   │   ├── test_correlation.py
│   │   ├── test_verification_agent.py
│   │   ├── test_investigator_agent.py
│   │   ├── test_search.py
│   │   ├── test_webhooks.py
│   │   └── test_chat.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/                        # (see Section 10.2)
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│   ├── PRD.md
│   ├── TECHNICAL_SPEC.md
│   ├── ROADMAP.md
│   └── PITCH_POSITIONING.md
│
├── .env.example
└── docker-compose.yml              # Local dev: Postgres + Redis + backend + frontend
```

---

## 13. Testing Strategy (TDD Workflow)

### Development Loop

Every feature is implemented using this enforced TDD cycle:

```
Write Test ──▶ Run Test (expect FAIL) ──▶ Implement Feature ──▶ Run Test ──▶ Pass? ──▶ Next Feature
                                                                   │
                                                                   ▼ (FAIL)
                                                              Fix Feature
                                                                   │
                                                                   ▼
                                                            Run Test Again
                                                                   │
                                                              ┌────┴────┐
                                                              │ Pass?   │
                                                              │ Yes ──▶ Next Feature
                                                              │ No  ──▶ Retry (max 3 attempts)
                                                              └─────────┘
                                                                   │
                                                              (After 3 fails)
                                                                   ▼
                                                         Log failure, skip feature,
                                                         create TODO for manual review
```

### Retry Safeguard

- **Max 3 fix attempts per test failure.** After 3, log to `BLOCKED.md` and move on.
- **Each attempt must change something.** Identical code counts as wasted attempt.
- **Blocked features are tracked** in `BLOCKED.md` for manual review.

### Test Categories

| Category | What It Tests | When It Runs |
|---|---|---|
| **Unit: Detection** | Pre-filter regex, LLM classification parsing, extraction parsing | After detection engine changes |
| **Unit: Correlation** | Scoring functions, merge logic, entity resolution | After correlation engine changes |
| **Unit: Search** | Vector search queries, reranking, context formatting | After search/RAG changes |
| **Unit: Agent Tools** | Individual tool functions return correct data | After tool implementation changes |
| **Integration: Verification Agent** | Agent correctly identifies verified/missing actions (mocked LLM) | After verification agent changes |
| **Integration: Investigator Agent** | Agent reasons through multi-step queries (mocked LLM) | After query agent changes |
| **Integration: Webhooks** | Slack/GitHub payload parsing, event normalization | After ingestion changes |
| **Integration: Pipeline** | Full event → detect → correlate → verify flow | After any pipeline changes |

### Test Tooling

- **Framework:** pytest + pytest-asyncio
- **Mocking:** LLM calls mocked with recorded responses (no real API calls in tests)
- **Database:** Test database (separate from dev) with fixtures
- **Coverage target:** Not enforced for hackathon, but test critical paths

---

## 14. Key Technical Decisions for MVP

| Decision | Choice | Rationale |
|---|---|---|
| Monolith vs microservices | Monolith with internal module boundary | Speed of dev; clean Backboard/Sense separation for future extraction |
| Sync vs async processing | Async (Celery) | Webhook handlers must return fast; LLM calls are slow |
| LLM gateway | Backboard API (external) | Abstracts provider SDKs; easy model swapping |
| Embedding model | Gemini `text-embedding-004` (768 dim) | Free tier available; good quality |
| LLM for classification/extraction | Gemini 2.0 Flash | Fast, cheap, good at structured output |
| LLM for verification agent | Gemini 2.0 Flash | Function calling capable, cost-effective |
| LLM for chat agent | Gemini 2.5 Pro | Strong reasoning for multi-step investigation |
| Agent framework | Gemini native function calling | No extra framework; simple loop with tool call handling |
| Agent iteration limit | 10 (verification), 8 (query) | Prevents runaway agent loops |
| Vector DB | pgvector (in PostgreSQL) | No extra infra; good enough for MVP scale |
| Primary UI | Chat with agent reasoning toggle | Shows both clean results and impressive internals |
| Frontend state | TanStack Query | Handles caching, pagination, SSE streaming well |
| Deployment | Railway | Managed Postgres + Redis + app hosting in one platform |
