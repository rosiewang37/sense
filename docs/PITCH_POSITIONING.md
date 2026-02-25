# Sense — Pitch Positioning & Competitive Analysis

**For hackathon pitch deck use only. Not part of the build spec.**
**Last Updated:** 2026-02-24

---

## Elevator Pitch

Engineering teams make hundreds of decisions across Slack, GitHub, and Google Drive — but none of it is connected. When someone asks "why did we switch suppliers?", nobody can find the answer. And worse — nobody checks if the decision was actually carried out.

Sense watches your tools in the background, automatically captures significant engineering moments, correlates events across platforms, dispatches AI agents to verify implementation, and makes your entire project history queryable through an investigative chat agent. Zero manual documentation.

---

## The Problem (For Slides)

- Engineering teams use 5–10 tools daily (Slack, GitHub, Drive, Jira, email, meetings)
- Critical knowledge is scattered across all of them
- **No tool connects knowledge across platform boundaries**
- When context is lost, teams re-discuss, re-decide, or make inconsistent choices
- **Decisions are made but never verified** — a Slack discussion says "switch suppliers" but nobody checks if the BOM was updated, the procurement ticket was created, or the spec was revised
- Hardware teams are hit hardest: mixed stacks, long cycles, physical consequences

---

## Why Existing Tools Don't Solve This

| Tool | What It Does | The Gap |
|---|---|---|
| **Microsoft Copilot** | Searches across M365 | Ecosystem-locked. Doesn't see Slack, GitHub, or Google Drive. |
| **Google Gemini** | Searches across Google Workspace | Same — doesn't see non-Google tools. |
| **Glean** ($7.2B) | Enterprise cross-platform search | **Finds documents but doesn't create knowledge.** Doesn't verify implementation. $50+/user, 100-user min. No hardware support. |
| **Slack AI** | Searches within Slack | Single tool. Can't verify a commit followed a decision. |
| **Atlassian Rovo** | Searches Atlassian ecosystem | Useless for non-Atlassian tools. |

### The Key Distinction

**Every existing tool is a search product.** They find information that already exists.

**Sense is a knowledge creation + verification product.** It creates structured knowledge from cross-tool activity AND dispatches agents to verify that decisions led to implementation. No other tool checks whether engineering decisions were actually followed through.

---

## Sense vs Glean (Detailed)

| Dimension | Glean | Sense |
|---|---|---|
| **Core function** | Search & discovery | Knowledge creation, verification & memory |
| **What it does with conversations** | Indexes and searches them in raw form | Extracts structured knowledge objects from them |
| **Cross-tool correlation** | Probabilistic ML inference ("these seem related") | Deterministic linking (Slack msg → GitHub commit → Drive file) |
| **Decision tracking** | None. CEO says "can't reliably capture the why" | Core feature — auto-extracts what, who, why |
| **Implementation verification** | None | Agents check if decisions were followed through across tools |
| **Knowledge creation** | Cannot create anything. Search-only. | Auto-creates structured records from activity |
| **Query approach** | RAG search (single-hop) | Multi-step investigative agent (reasons through multiple sources) |
| **Hardware team support** | None. Software engineering only. | Built for mixed-stack engineering teams |
| **Target market** | 500+ employee enterprises | 20–100 person engineering teams |
| **Pricing** | $50+/user/month, 100-user min (~$60K/yr) | $10–50/user/month, no minimum |

**One-liner for judges:** "Glean finds your documents. Sense remembers your decisions and checks if they were followed through."

---

## Target Market Positioning

### Why Mid-Size (20-100) Engineering Teams?

- **Too small for Glean** — can't justify $60K/year minimum
- **Too cross-platform for Copilot/Gemini** — use Slack + GitHub + Google Drive
- **Hardware teams specifically** — mixed stacks, physical consequences, regulatory traceability

### Beachhead → Expansion

1. **Start:** Hardware/mechanical engineering teams (20–100 people) with mixed tool stacks
2. **Expand:** Any engineering team (software, firmware, systems) with cross-platform tools
3. **Long-term:** Any team that needs cross-tool knowledge management + verification

---

## Demo Talking Points

When showing the demo, emphasize these moments:

1. **"Zero effort"** — The team changes nothing about how they work. Sense runs in the background.

2. **"Cross-tool"** — Point out the Knowledge Object linking a Slack message AND a GitHub commit. No other tool at this price point does this.

3. **"Verification"** — This is the big differentiator. Show the verification panel: "BOM updated ✅, Procurement ticket ❌ Missing." No other tool checks if decisions were followed through.

4. **"Investigative agent"** — Toggle the reasoning ON. Show the agent thinking: "Searching knowledge base... found decision... checking raw Slack events for more context... checking verification status..." This is visibly more intelligent than keyword search.

5. **"Ask why, not where"** — Don't ask "find the motor document." Ask "WHY did we switch motor suppliers?" The answer includes evidence from multiple tools AND implementation status.

---

## Anticipated Judge Questions

| Question | Answer |
|---|---|
| "How is this different from Glean?" | Glean is enterprise search — it finds existing documents. Sense creates new structured knowledge, correlates events across tools, and verifies implementation with AI agents. Glean costs $60K/year minimum. |
| "Why would teams use this instead of a wiki?" | Wikis require someone to write and maintain them — they go stale immediately. Sense requires zero manual effort. It also does something wikis can't: verify that documented decisions were actually implemented. |
| "What about privacy?" | Everything is opt-in. Teams choose exactly which channels, repos, and folders to monitor. They can redact or delete any captured knowledge. |
| "How is the verification agent different from a simple checklist?" | The agent uses semantic search across tools to find evidence — it doesn't require predefined checklists. It infers expected follow-ups from the decision content and searches for evidence autonomously. |
| "Can the agents hallucinate?" | Agents only report evidence they find in connected tools. They mark actions as "verified" only with specific evidence (commit hash, file name). When unsure, they report "unknown" rather than guessing. |
| "Can this scale?" | The pre-filter eliminates 85% of events before any LLM call. Verification agents are async (Celery tasks). Architecture is queue-based and horizontally scalable. |
| "What's the business model?" | SaaS subscription, $10–50/user/month. Target 20–100 person teams. Backboard.io can also be offered as a standalone API platform for developers building AI memory features. |
| "How do you prevent agent loops?" | Hard cap: verification agents max 10 tool calls, query agents max 8. After the cap, they return whatever they've found. Blocked features are logged, not retried infinitely. |

---

## Product Vision

Sense is a **cross-platform engineering memory with active verification**. It watches workflows across tools, automatically captures and correlates related events, verifies whether decisions led to implementation, and surfaces gaps and suggested follow-up actions — all without requiring any manual documentation.

**One-liner:** *Your team's engineering memory — captured, verified, and queryable across every tool.*

### The Five Capabilities

```
1. CAPTURE   — Auto-detect decisions, changes, and approvals from cross-tool activity
2. CORRELATE — Link related events across Slack, GitHub, and Drive into unified records
3. VERIFY    — Agents check whether decisions were actually implemented across tools
4. SUGGEST   — Agents recommend follow-up actions for gaps they find
5. QUERY     — Chat interface to ask anything about project history
```

### What Sense Does That Search Cannot

- Search finds documents. Sense finds **context** — linking a Slack thread to the GitHub commit it triggered to the file that was uploaded as a result.
- Search requires you to know what to look for. Sense lets you ask **why** something happened and get evidence from multiple sources.
- Search is reactive. Sense **continuously structures** knowledge in the background so it's ready when you need it.
- Search discovers existing content. Sense **creates new structured knowledge** from unstructured cross-tool activity.
- Search never follows up. Sense **verifies implementation** and flags when decisions haven't been acted on.

---

## Problem Statement (Detailed)

Engineering teams — especially in hardware, mechanical, and cross-disciplinary fields — generate critical knowledge across scattered tools every day: Slack threads, GitHub commits, Google Drive uploads, Jira tickets, email chains, and meeting calls. This knowledge is **never unified**. It lives fragmented across platforms, buried in message histories and file versions.

Two problems compound on each other:

1. **Knowledge is fragmented.** When someone asks *"Why did we switch motor suppliers?"*, the answer requires manually searching through months of Slack messages, scrolling GitHub histories, and digging through Drive folders. This costs hours and frequently fails entirely.

2. **Decisions are made but never followed through.** A team decides to switch suppliers in a Slack thread, but nobody updates the BOM in GitHub. The qualification report never gets uploaded. The procurement ticket never gets created. There is no system that checks whether decisions led to actual implementation across tools.

**The core insight:** The information already exists in observable digital workflows. The problem isn't that teams don't create knowledge — it's that no tool connects knowledge across platform boundaries, structures it automatically, and verifies that decisions were actually acted on.

---

## Target Users

### Primary Persona: Mid-Size Engineering Teams (20–100 people)

- **Industry:** Mechanical engineering, hardware development, robotics, manufacturing, aerospace, automotive
- **Pain:** Cross-platform tool usage (can't standardize on just Microsoft or just Google), high knowledge velocity, expensive consequences of lost context
- **Budget:** Can justify $10–50/user/month for productivity tooling

### Secondary Persona: Team Leads & Engineering Managers

- Need to reconstruct context for onboarding, audits, postmortems, and design reviews
- Need visibility into whether team decisions are being followed through
- Currently maintain personal notes or wikis that go stale immediately

### Why Hardware/Mechanical Engineering?

These teams are uniquely underserved because:
1. **Mixed tool stacks are unavoidable.** CAD in Onshape, code in GitHub, docs in Google Drive, communication in Slack, project tracking in Jira. No single vendor covers this.
2. **Decisions have physical consequences.** Choosing the wrong motor supplier costs months and real money, not just a code revert.
3. **Regulatory traceability.** Many hardware industries require design decision documentation for compliance (ISO, FDA, aerospace). Currently done manually.
4. **Long project cycles.** A 12-month hardware project generates far more "forgotten context" than a 2-week sprint.
5. **Follow-through gaps are expensive.** A decision made in Slack but never implemented in the BOM or procurement system can delay production by weeks.

---

## What Sense Is NOT

- **Not a search engine.** Search finds documents by keywords. Sense understands context, relationships, and history across tools — creates structured knowledge and verifies implementation.
- **Not a project management tool.** It doesn't replace Jira or Asana. It captures the *why* behind work and checks if it was followed through.
- **Not an AI judge.** Verification agents check whether actions were taken, not whether decisions were correct. Sense never evaluates decision quality.
- **Not a meeting transcription service.** It can consume transcripts but doesn't generate them.
- **Not a wiki.** It doesn't require anyone to write or maintain documentation.

---

## Success Metrics (Hackathon Demo)

| Metric | Target |
|---|---|
| Knowledge extraction precision | > 70% (flagged items are genuinely significant) |
| Cross-tool correlation accuracy | > 60% (correctly merges related events) |
| Verification accuracy | > 50% (correctly identifies implemented vs missing follow-ups) |
| Chat query answer relevance | Qualitatively good in demo scenarios |
| Agent reasoning quality | Agent takes sensible investigative steps (not random) |
| Time from event to Knowledge Object | < 5 minutes |
| Zero manual input required | True for core capture + verification flow |

---

## Risks & Open Questions

| Risk | Mitigation |
|---|---|
| NLP extraction accuracy may be low | Start with high-precision / low-recall; let users confirm/reject to improve over time |
| Cross-tool correlation may produce false merges | Show correlation confidence; allow users to split/merge manually |
| Verification agents may infer wrong expected actions | Show verification as suggestions, not requirements; let users dismiss/edit |
| Agent reasoning may be slow or costly | Use Haiku for verification, Sonnet only for chat; cache agent tool results |
| Privacy concerns — monitoring team communications | Strict opt-in per channel/repo/folder; clear data retention policies; redaction tools |
| API costs for LLM processing at scale | Pre-filter eliminates ~85% of events before LLM; use cheapest viable models; batch processing |
| "Creepy factor" — monitoring discomfort | Transparent dashboard showing exactly what's monitored; easy opt-out; team admin controls |
