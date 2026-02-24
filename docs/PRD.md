# Backboard — Product Requirements Document

**Version:** 0.1 (Hackathon MVP)
**Last Updated:** 2026-02-24
**Domain:** backboard.io

---

## 1. Problem Statement

Engineering teams — especially in hardware, mechanical, and cross-disciplinary fields — make hundreds of decisions per week across scattered tools: Slack threads, email chains, GitHub commits, Google Drive uploads, Jira tickets, and meeting calls. These decisions are **never formally documented**. They live in ephemeral message histories and personal memory.

When someone asks *"Why did we switch motor suppliers?"* or *"Who approved the power budget change?"*, the answer requires manually digging through months of Slack messages, email threads, and meeting recordings. This costs hours and frequently fails entirely.

**The core insight:** decisions already happen in observable digital workflows. The problem isn't that teams don't document — it's that the documentation burden is too high. If a system could *watch* those workflows and *automatically* identify and structure decisions, the problem disappears.

---

## 2. Product Vision

Backboard is a **background intelligence layer** for engineering teams. It observes workflows across tools, identifies decision moments using NLP, and converts them into structured, queryable, persistent **knowledge objects** — without requiring any manual documentation effort from the team.

**One-liner:** *Your team's engineering decisions, captured automatically, queryable forever.*

---

## 3. Target Users

### Primary Persona: Mid-Size Engineering Teams (20–100 people)

- **Industry:** Mechanical engineering, hardware development, robotics, manufacturing, aerospace, automotive
- **Pain:** Cross-platform tool usage (can't standardize on just Microsoft or just Google), high decision velocity, expensive consequences of lost context
- **Budget:** Can justify $10–50/user/month for productivity tooling
- **Why not small teams?** Decisions are fewer and tribal knowledge still works at <15 people. Cost per seat is harder to justify.
- **Why not enterprise first?** Compliance (SOC 2, SSO, audit logs) and procurement cycles add 6–12 months of non-product work.

### Secondary Persona: Team Leads & Engineering Managers

- Need to understand decision history for onboarding, audits, and postmortems
- Currently maintain personal notes or wikis that go stale immediately

---

## 4. Core Concepts

### 4.1 Decision Object (Knowledge Object)

The atomic unit of Backboard. A structured record representing a single engineering decision.

```
{
  "id": "dec_8f3a...",
  "title": "Switch primary motor supplier to MotorCo",
  "summary": "Team decided to switch from SupplierA to MotorCo due to 30% cost reduction and better lead times.",
  "decision_statement": "We will use MotorCo as our primary motor supplier starting Q2.",
  "rationale": "MotorCo offers 30% lower unit cost, 2-week lead times vs 6-week, and passed qualification testing.",
  "alternatives_considered": [
    "Stay with SupplierA (rejected: cost too high)",
    "Dual-source between both (rejected: complexity not justified at current volume)"
  ],
  "participants": ["alice@company.com", "bob@company.com"],
  "artifacts": [
    { "type": "slack_thread", "url": "https://slack.com/...", "snippet": "..." },
    { "type": "github_commit", "url": "https://github.com/...", "message": "Update BOM with MotorCo parts" },
    { "type": "google_drive_file", "url": "https://drive.google.com/...", "name": "MotorCo_Qualification_Report.pdf" }
  ],
  "timestamp": "2026-02-20T14:32:00Z",
  "confidence": 0.87,
  "status": "active",
  "tags": ["supply-chain", "motors", "cost-reduction"],
  "project": "proj_rover_v2"
}
```

### 4.2 Cross-Tool Event Correlation

The key differentiator. When a user:

1. Sends a Slack message: *"I've finalized the motor supplier switch, uploading the qualification report now"*
2. Uploads `MotorCo_Qualification_Report.pdf` to Google Drive
3. Commits a BOM update to GitHub
4. Mentions progress in a standup meeting

Backboard **correlates these events** into a single Decision Object using:

- Temporal proximity (events within a configurable time window)
- Participant overlap (same person or team involved)
- Semantic similarity (NLP embedding comparison of content)
- Explicit references (URLs, file names, @mentions)

### 4.3 Queryable Project Memory

Users interact with accumulated decisions through:

- **Dashboard:** Browse, filter, and search decisions by project, date, participant, or tag
- **Chat Interface:** Natural language queries like *"Why did we approve the power budget?"* that return structured answers with linked evidence
- **Optional Browser Extension:** Click to include a specific document or folder into Backboard's monitoring scope

---

## 5. Key Features

### 5.1 Automatic Decision Detection (P0 — MVP)

- Continuous monitoring of connected tool streams
- NLP-based detection of "decision language" patterns:
  - Declarative statements: *"We've decided to...", "Going with...", "Final call:..."*
  - Approval patterns: *"Approved", "LGTM", "Sign-off on..."*
  - Change announcements: *"Switching to...", "Moving from X to Y"*
  - Rejection patterns: *"We're not going with...", "Ruling out..."*
- Structured extraction: what, who, why, when, and linked artifacts
- Confidence scoring (low-confidence decisions flagged for human review)

### 5.2 Cross-Tool Correlation Engine (P0 — MVP)

- Merges related events from multiple sources into unified Decision Objects
- Time-window-based grouping with semantic similarity validation
- Entity resolution across tools (matching users across Slack, GitHub, email)

### 5.3 Decision Dashboard (P0 — MVP)

- Chronological and filterable list of all captured decisions
- Decision detail view with full context and linked artifacts
- Project-level grouping
- Status management (active / superseded / reversed)

### 5.4 Chat Query Interface (P0 — MVP)

- Natural language questions about project history
- Returns structured answers with evidence citations
- RAG-based retrieval over decision objects and their source artifacts

### 5.5 Integration Connectors (P0 — MVP, subset)

| Integration        | MVP | Post-MVP |
|--------------------|-----|----------|
| Slack              | Yes |          |
| GitHub             | Yes |          |
| Google Drive       | Yes |          |
| Microsoft Teams    |     | Yes      |
| Email (Gmail/O365) |     | Yes      |
| Jira               |     | Yes      |
| Meeting Transcripts (Zoom/Teams) | | Yes |

### 5.6 Browser Extension (P1 — Post-MVP)

- Click to include/exclude specific documents, folders, or channels
- Inline indicator showing when a decision has been captured from the current page

### 5.7 User Controls & Privacy (P1 — MVP-lite)

- Users can define which channels/repos/folders to monitor
- Ability to redact or delete captured decisions
- Per-integration enable/disable toggles
- Audit log of what was captured and when

---

## 6. User Flows

### 6.1 Onboarding (MVP)

1. Sign up at backboard.io
2. Connect integrations (OAuth for Slack, GitHub, Google Drive)
3. Select which channels, repos, and folders to monitor
4. Backboard begins processing historical data (backfill) and live streams

### 6.2 Passive Operation (Daily)

1. Team works normally — no behavior change required
2. Backboard processes events in the background
3. New Decision Objects appear on the dashboard
4. Low-confidence decisions are flagged for optional human review

### 6.3 Querying (On-Demand)

1. User opens Backboard dashboard
2. Browses decision feed or opens chat interface
3. Asks: *"What did we decide about the battery thermal solution?"*
4. Gets structured answer with linked Slack threads, documents, and commits

### 6.4 Decision Review (Optional)

1. User receives notification of a new captured decision
2. Reviews the auto-generated summary
3. Optionally edits, confirms, or dismisses it
4. Confirmed decisions get boosted confidence for future pattern learning

---

## 7. Success Metrics

| Metric | Target (MVP / Hackathon Demo) |
|--------|-------------------------------|
| Decision detection precision | > 70% (of flagged items are real decisions) |
| Decision detection recall | > 50% (captures at least half of actual decisions) |
| Cross-tool correlation accuracy | > 60% (correctly merges related events) |
| Query answer relevance | Qualitatively good in demo scenarios |
| Time from event to Decision Object | < 5 minutes |
| Zero manual input required | True for core flow |

---

## 8. What Backboard Is NOT

- **Not a project management tool.** It doesn't replace Jira or Asana. It captures the *why* behind tickets, not the tickets themselves.
- **Not a meeting transcription service.** It consumes transcripts but doesn't generate them.
- **Not a search engine.** It doesn't index all documents — only decision-relevant content.
- **Not an approval workflow.** It observes decisions after they happen; it doesn't enforce process.

---

## 9. Risks & Open Questions

| Risk | Mitigation |
|------|------------|
| NLP decision detection accuracy may be low | Start with high-precision / low-recall; let users confirm/reject to improve over time |
| Cross-tool correlation may produce false merges | Show correlation confidence; allow users to split/merge manually |
| Privacy concerns — monitoring team communications | Strict opt-in per channel/repo/folder; clear data retention policies; redaction tools |
| API costs for LLM processing at scale | Use cheapest viable models (Claude Haiku, GPT-4o-mini); batch processing; cache embeddings |
| Integration maintenance burden | Start with 3 integrations; use official APIs with webhook-first architecture |
| "Creepy factor" — team members uncomfortable with monitoring | Transparent dashboard showing exactly what's monitored; easy opt-out; focus on team-level benefit |

---

## 10. MVP Scope (Hackathon)

For the hackathon demo, Backboard should demonstrate:

1. **Live ingestion** from Slack + GitHub (+ Google Drive if time allows)
2. **Automatic detection** of at least 3 decision types from a prepared demo dataset
3. **Cross-tool correlation** — show one decision stitched from a Slack message + GitHub commit + uploaded file
4. **Dashboard** — browsable decision feed with detail view
5. **Chat query** — ask a question, get an answer with evidence

**Out of scope for hackathon:** email, Teams, Jira, meeting transcripts, browser extension, user auth beyond basic login, mobile, self-hosted deployment.
