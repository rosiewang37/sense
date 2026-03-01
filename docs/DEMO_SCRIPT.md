# Sense — Demo Video Script

**Target length:** 3–4 minutes  
**Tone:** Concise, confident, conversational  
**Setup:** App running locally — frontend at `localhost:5173`, backend at `localhost:8000`

---

## Video Structure

| Section | Duration | What to show |
|---|---|---|
| 1. Hook | ~15s | State the problem |
| 2. Slack → Knowledge Object | ~45s | Send Slack message, show auto-extraction |
| 3. GitHub → Cross-tool correlation | ~45s | Push a commit, show it linked to the Slack decision |
| 4. Verification panel | ~30s | Show verified vs missing follow-ups |
| 5. Investigative chat | ~60s | Ask questions, show agent reasoning |
| 6. Dashboard walkthrough | ~30s | Filter, browse, detail view |
| 7. Close | ~15s | Recap the five capabilities |

---

## Section 1 — Hook (15s)

> **Say:** "Engineering teams make decisions all day across Slack and GitHub — but none of it is connected, and nobody checks if those decisions were actually followed through. Sense fixes that. Let me show you."

**Screen:** Start on the Sense chat page (empty state showing "Ask Sense anything").

---

## Section 2 — Slack Ingestion (45s)

### Slack message to send

Post this in your monitored Slack channel:

> **Message 1:**
> ```
> After testing both options, we're going with MotorCo as our primary motor supplier for Rover V2. They're 30% cheaper than SupplierA and lead times are 2 weeks vs 6. @bob please update the BOM in GitHub and create a procurement ticket. @carol upload the qualification report to Drive.
> ```

> **Say:** "A team member posts a decision in Slack — totally normal workflow, nothing extra required. In the background, Sense picks it up, classifies it as a decision, and extracts a structured Knowledge Object automatically."

**Screen:** Switch to the Slack channel, send the message. Then switch to the Sense Knowledge Feed page. Refresh or wait briefly for the new KO to appear.

> **Say:** "Here it is — Sense captured the decision, identified participants, and inferred three expected follow-up actions. No one typed this up manually."

---

## Section 3 — GitHub Commit + Cross-Tool Correlation (45s)

### GitHub commit to make

In your monitored repo, commit a file that references the supplier change:

```bash
git checkout -b motorco-bom-update
echo "MotorCo M-200 | Qty: 4 | Unit: $45" >> bom.csv
git add bom.csv
git commit -m "Update BOM with MotorCo M-200 motor parts for Rover V2"
git push origin motorco-bom-update
```

> **Say:** "Now a teammate pushes a commit updating the BOM. Sense picks up the GitHub webhook, sees it's semantically related to the Slack decision — same topic, overlapping actors, within the time window — and automatically correlates them into a single Knowledge Object."

**Screen:** Show the Knowledge Feed — the KO now shows artifacts from both Slack and GitHub.

> **Say:** "One record, two sources. That's cross-tool correlation."

---

## Section 4 — Verification Panel (30s)

**Screen:** Click into the Knowledge Object detail page. Scroll to the Verification Panel.

> **Say:** "Here's where Sense goes further than search. The verification agent automatically checked whether the decision's follow-ups were completed. BOM updated — verified, with commit evidence. Procurement ticket — missing. Qualification report — missing. It tells you what's done and what's not, and suggests next steps."

---

## Section 5 — Investigative Chat (60s)

**Screen:** Navigate to the Chat page. Make sure "Agent Reasoning" toggle is **ON**.

### Chat prompts to type (in order):

**Prompt 1:**
```
Why did we switch motor suppliers?
```

> **Say:** "Now the real power — the investigative chat. I'll ask a natural language question."

**Wait for the response to stream in. Point out the agent reasoning steps as they appear.**

> **Say:** "Watch the agent work — it searches the knowledge base, finds the decision, pulls in the original Slack context, checks the verification status, and synthesizes it all into one answer with evidence."

---

**Prompt 2:**
```
Was the BOM actually updated?
```

> **Say:** "I can drill deeper. Sense doesn't just say 'yes' — it cites the specific commit."

---

**Prompt 3:**
```
What's still missing from the motor supplier switch?
```

> **Say:** "And I can ask about gaps. The agent pulls up verification checks and tells me exactly what hasn't been done yet — procurement ticket and qualification report."

---

## Section 6 — Dashboard Walkthrough (30s)

**Screen:** Navigate to the Knowledge Feed page.

> **Say:** "The dashboard gives you a browsable feed of everything Sense has captured. You can filter by type — decisions, changes, approvals — and each card shows the verification status at a glance."

**Action:** Use the type filter to select "decision". Click into one KO to show the detail view.

> **Say:** "Click into any item for the full context — what was decided, why, who was involved, linked artifacts from Slack and GitHub, and the verification checklist."

---

## Section 7 — Close (15s)

> **Say:** "That's Sense — capture, correlate, verify, suggest, and query — all automatic, all cross-platform, zero manual documentation. Your team's engineering memory."

---

## Quick Reference: All Sample Inputs

### Slack messages

| # | Message |
|---|---|
| 1 | `After testing both options, we're going with MotorCo as our primary motor supplier for Rover V2. They're 30% cheaper than SupplierA and lead times are 2 weeks vs 6. @bob please update the BOM in GitHub and create a procurement ticket. @carol upload the qualification report to Drive.` |

### GitHub actions

| # | Action | Command |
|---|---|---|
| 1 | BOM update commit | `git commit -m "Update BOM with MotorCo M-200 motor parts for Rover V2"` |

### Chat prompts

| # | Prompt |
|---|---|
| 1 | `Why did we switch motor suppliers?` |
| 2 | `Was the BOM actually updated?` |
| 3 | `What's still missing from the motor supplier switch?` |
