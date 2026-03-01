# Manual Testing Plan

Step-by-step guide. Every message is ready to copy-paste into Slack.

## Prerequisites

- Backend running with a valid `BACKBOARD_API_KEY`
- Slack webhook reachable
- `SLACK_BOT_TOKEN` set in `.env`
- A test Slack channel (e.g. `#sense-testing`)
- A test GitHub repo connected to the webhook

---

## Test 1: Simple Decision Extraction

**Goal:** Confirm a single decision message creates a KO.

**Steps:**

1. Go to your test Slack channel.
2. Send **one** of these messages (pick any):

```
We've decided to migrate our primary database from MySQL to CockroachDB for horizontal scaling.
```

```
Final decision: we're replacing NGINX with Caddy as our reverse proxy for automatic TLS.
```

```
We've decided to drop Elasticsearch and move all full-text search to Typesense.
```

```
Let's go with Turborepo for our monorepo build system instead of Nx.
```

3. Wait ~10 seconds for the backend to process.
4. Open the Knowledge page in the UI.

**Expected:**

- A new decision KO appears with a title matching your topic.
- Clicking it shows the detail page with a summary and statement.

**Remember which message you sent** — you'll use the same topic for Test 5.

---

## Test 2: Multi-Message Context (Dynamic Update)

**Goal:** Confirm that follow-up messages dynamically update the decision's context after the KO is already created.

**Important:** Use a **different topic** from Test 1 so the two decisions stay separate.

Pick **one** option below. Send each line as a **separate Slack message**, in order, waiting 2-3 seconds between each.

### Option A — Logging Stack

Message 1:
```
Our ELK stack is eating 40% of the infra budget and nobody looks at half the dashboards.
```

Message 2:
```
Grafana Loki with S3 storage would cut that cost by 80% and still give us structured log queries.
```

Message 3 (the decision):
```
Final decision: we're replacing the ELK stack with Grafana Loki for all application logging.
```

Message 4 (follow-up):
```
I'll start the migration with the payments service logs this sprint.
```

### Option B — Container Runtime

Message 1:
```
Docker Desktop licensing is getting expensive now that we have 60 engineers.
```

Message 2:
```
Podman is drop-in compatible and doesn't need a daemon or a paid license.
```

Message 3 (the decision):
```
We've decided to standardize on Podman instead of Docker Desktop for local development.
```

Message 4 (follow-up):
```
I'll update the onboarding docs and dev setup scripts by end of week.
```

### Option C — Feature Flags

Message 1:
```
LaunchDarkly's pricing tier jump is brutal for our current usage.
```

Message 2:
```
Unleash is open-source, self-hosted, and covers every flag pattern we use today.
```

Message 3 (the decision):
```
We've decided to switch our feature flag system from LaunchDarkly to self-hosted Unleash.
```

Message 4 (follow-up):
```
I'll set up the Unleash instance on our k8s cluster and migrate the first 10 flags this week.
```

**Steps:**

1. Send messages 1-4 in order (separate messages, 2-3 sec apart).
2. After message 3 is sent, wait ~10 seconds. Check the Knowledge page — a new KO should appear.
3. After message 4 is sent, wait ~10 seconds.
4. Click into the KO detail page and click **Show Context**.

**Expected after message 3:**

- A decision KO is created.
- The context panel shows messages 1 and 2 as preceding context.
- Message 3 is highlighted in blue as the trigger.

**Expected after message 4:**

- The context panel auto-refreshes (within 5 seconds).
- Message 4 now appears as a following message in the surrounding context.
- The KO's participants list includes the person who sent message 4.
- Backend logs show: `Linked event ... as context to KO ... and re-enriched source event`

---

## Test 3: Attachment Metadata

**Goal:** Confirm file attachments are captured in the decision context.

**Steps:**

1. Create or find any small file (PDF, image, text file — doesn't matter).
2. In your test Slack channel, upload the file and add this message:

```
We've decided to adopt the attached runbook template for all production incident responses.
```

3. Wait ~10 seconds, then open the KO detail page.
4. Click **Show Context**.

**Expected:**

- The context panel shows an **Attachments** section with the file name and type.
- If the file was a PDF, it shows the `.pdf` filetype label.

---

## Test 4: Decision-Maker Name Resolution

**Goal:** Confirm the decision author's display name (not Slack user ID) is shown.

**Steps:**

1. From your own Slack account (not a bot), send:

```
Final decision: we're moving our scheduled jobs from cron to Temporal for workflow orchestration.
```

2. Wait ~10 seconds, then open the KO detail page.
3. Click **Show Context**.

**Expected:**

- The **Author** field shows your real name (e.g. "Jane Smith"), not a Slack user ID like `U04ABCDEF`.
- The event metadata includes `actor_display_name`.

---

## Test 5: GitHub Commit Links to Existing Decision

**Goal:** Confirm a GitHub commit is automatically linked as evidence to a matching Slack decision.

**Steps:**

1. Make sure a decision KO from Test 1 already exists. Check which topic you used.
2. In your connected GitHub repo, create a commit with a **matching** message. Pick the one that matches your Test 1 decision:

If you used the MySQL/CockroachDB decision:
```
git commit --allow-empty -m "Migrate primary database from MySQL to CockroachDB"
```

If you used the NGINX/Caddy decision:
```
git commit --allow-empty -m "Replace NGINX with Caddy reverse proxy for automatic TLS"
```

If you used the Elasticsearch/Typesense decision:
```
git commit --allow-empty -m "Switch full-text search backend from Elasticsearch to Typesense"
```

If you used the Turborepo decision:
```
git commit --allow-empty -m "Adopt Turborepo for monorepo build pipeline"
```

3. Push the commit: `git push`
4. Wait ~15 seconds for the webhook to fire and the backend to process.
5. Open the **same KO from Test 1** in the detail page. Click **Show Context**.

**Expected:**

- The KO detail page now shows a second linked event with a `github_evidence` badge.
- The GitHub commit content is visible in the context panel.
- **No new standalone KO** was created for the commit.
- Backend logs show: `GitHub event ... linked as evidence to KO ...`

---

## Test 6: Unrelated GitHub Commit Does Not Link

**Steps:**

1. Push a commit with this message:

```
git commit --allow-empty -m "Fix typo in README and update contributing guidelines"
```

2. Push: `git push`
3. Wait ~15 seconds.

**Expected:**

- The commit is ingested as an event.
- It does **not** link to any existing decision KO.
- No decision KO is created for it.

---

## Test 7: Chat — Query a Known Decision

**Steps:**

1. Open the Chat page in the UI.
2. Ask about the topic you used in Test 1. Copy one of these:

If MySQL/CockroachDB:
```
What did we decide about our database?
```

If NGINX/Caddy:
```
What decisions have we made about our reverse proxy?
```

If Elasticsearch/Typesense:
```
Have we made any decisions about search infrastructure?
```

If Turborepo:
```
What did we decide about our build system?
```

**Expected:**

- The agent finds and references the matching decision KO.
- The answer includes the specific technology choice from your decision.

---

## Test 8: Chat — Follow-Up Query

**Steps:**

1. Immediately after Test 7, in the same chat session, ask:

```
Why did we make that change?
```

**Expected:**

- The answer references the same decision (not a different one).
- If the original Slack messages included rationale, it's mentioned.
- If no rationale was stated, the agent says so honestly.

---

## Test 9: Chat — Service Failure Fallback

**Steps:**

1. Temporarily set an invalid `BACKBOARD_API_KEY` in your `.env` and restart the backend.
2. Ask in chat:

```
What decisions have we made recently?
```

3. After testing, restore the real API key and restart.

**Expected:**

- Backend logs show the Backboard error with a traceback.
- The chat still returns a useful fallback answer from direct DB search.
- The UI does **not** just show "Sorry, something went wrong."

---

## Test 10: Two Related Decisions Merge

**Steps:**

1. Send this message:

```
We've decided to use Prometheus for all backend service metrics collection.
```

2. Wait 30 seconds, then send:

```
Final decision: Prometheus will be our standard metrics and alerting stack going forward.
```

3. Wait for the correlation job to run (every 2 minutes), or trigger it manually.

**Expected:**

- Two KOs appear initially.
- After correlation runs, the lower-confidence KO is marked as `merged`.
- Only one active KO remains on the Knowledge page.

---

## Test 11: Different Topics Do Not Merge

**Steps:**

1. Send these two messages 30 seconds apart:

```
We've decided to use Prometheus for all backend service metrics collection.
```

```
We've decided to replace our REST API gateway with GraphQL using Apollo Server.
```

**Expected:**

- Both KOs stay `active` — they are not merged.

---

## Test 12: Casual Messages Do Not Create KOs

**Steps:**

Send each of these as separate messages:

```
Has anyone tried the new cafe downstairs?
```

```
Can someone review my PR when you get a chance?
```

```
The staging deploy is taking forever today.
```

**Expected:**

- No KOs are created for any of these.
- The pre-filter rejects them (check backend logs for `PRE-FILTER rejected`).

---

## Test 13: Vague Discussion Does Not Create a KO

**Steps:**

Send:

```
We should probably evaluate Pulumi vs Terraform again before the next infra sprint.
```

**Expected:**

- May pass the pre-filter (technical language).
- The classifier rejects it — no firm decision was made.
- No KO is created.

---

## Quick Inspection Checklist

After each test, you can verify:

| What to check | Where |
|---|---|
| KO appeared or not | Knowledge page in the UI |
| Context messages captured | KO detail page → Show Context |
| Attachments captured | KO detail page → Show Context → Attachments section |
| GitHub evidence linked | KO detail page → Show Context → look for `github_evidence` badge |
| Actor name resolved | KO detail page → Show Context → Author field |
| Backend processing logs | Terminal running the backend |
| Dynamic context update | KO detail page auto-refreshes every 5s |

## Regression Checklist

After all tests pass:

1. Slack webhook still returns `{"ok": true}` quickly (no blocking).
2. GitHub ingestion creates or links events normally.
3. Chat history persists across page navigation.
4. No raw datetime objects in agent tool responses.
5. Existing KOs from Test 1 are not corrupted by later tests.
