# Manual Testing Plan

This plan is meant to validate the chat fix, Slack decision extraction, surrounding-context enrichment, and GitHub correlation behavior.

## Prerequisites

- Backend is running with a valid `BACKBOARD_API_KEY`.
- Slack webhook is reachable by Slack.
- `SLACK_BOT_TOKEN` is set if you want surrounding-message and attachment enrichment.
- A test Slack channel exists where you can send controlled messages.
- A test GitHub repo is connected to the GitHub webhook.

## Slack Decision Tests

### Test 1: Simple Decision Extraction

Pick any one of these exact Slack messages:

```text
We've decided to move frontend deployment from Vercel to Cloudflare Pages.
Final decision: we'll standardize on Auth0 for SSO instead of maintaining custom OAuth.
We've decided to switch CI from GitHub-hosted runners to self-hosted runners for build speed.
Let's go with Sentry for frontend error tracking instead of relying on console logs.
We've decided to move the API worker queue from Celery to Redis Streams.
```

Expected result:

- The regex pre-filter matches.
- The classifier marks the event as significant.
- A decision KO is created.
- The KO title and summary mention the selected topic.

### Test 2: Multi-Message Context Around a Decision

Use one of these short Slack discussions and send the messages in order from different users.

```text
Option A
Maya: Vercel preview builds are timing out on large branches.
Jon: Cloudflare Pages would cut deploy time and lower cost.
Rina: We've decided to move frontend deployment to Cloudflare Pages.
Maya: I'll update the DNS and preview environment setup tomorrow.

Option B
Diego: Datadog costs are climbing and most of our alerts are noisy.
Leah: Grafana Cloud gives us enough logs and dashboards for this stage.
Noah: Final decision: we'll consolidate app monitoring in Grafana Cloud.
Diego: I'll migrate the on-call dashboards this week.

Option C
Priya: Our current OAuth flow is too brittle for enterprise logins.
Alex: Auth0 will remove a lot of edge-case maintenance.
Sam: We've decided to standardize on Auth0 for SSO.
Priya: I'll update the login rollout checklist tomorrow.
```

Expected result:

- Only the decision message should create the KO.
- The stored event metadata should include `context_messages`.
- The extraction prompt should receive preceding and following messages, not just the trigger line.
- KO participants should include the named people captured from context, plus the author.
- Open the created knowledge object from the Knowledge feed.
- Click `Show Context` in the `Decision Context` panel.
- Confirm the panel shows the surrounding messages and highlights the trigger message.

### Test 3: Attachment Metadata Included

Send a Slack message with an attached file and this exact text:

```text
We've decided to use the attached incident handoff checklist for the on-call rotation.
```

Use a file named:

```text
incident-handoff-checklist.pdf
```

Expected result:

- `metadata.file_ids` is captured by the Slack parser.
- If `SLACK_BOT_TOKEN` is configured, `metadata.attachments` is populated with file metadata.
- The extraction context includes a "Shared attachments" section.
- In the Knowledge detail page, `Show Context` should reveal the attachment entry inside the `Decision Context` panel.

### Test 4: Decision-Maker Name Resolution

Send a Slack decision message from a real Slack user account:

```text
Final decision: we are moving the API worker queue to Redis Streams.
```

Expected result:

- The stored event metadata includes `actor_display_name`.
- The event uses the resolved human-readable name during extraction.
- Chat search results for raw events show a real name instead of only a Slack user ID.

## GitHub Correlation Tests

### Test 5: GitHub Commit Links To Existing Slack Decision

First create one of the Slack decisions from Test 1. Then, within 7 days, push a matching commit message such as one of these:

```text
Move frontend deployment from Vercel to Cloudflare Pages
Adopt Auth0 for SSO and retire custom OAuth handling
Switch API workers from Celery to Redis Streams
Standardize frontend error tracking on Sentry
```

Expected result:

- The GitHub event is ingested.
- The event is compared to recent decision KOs from the last 7 days.
- If the correlation score is at least `0.45`, the GitHub event is linked to the matching Slack decision KO as `github_evidence`.
- No duplicate standalone KO should be created for the commit when a strong link is found.

### Test 6: Unrelated GitHub Commit Does Not Link

Push a commit with this exact message:

```text
Update README formatting and fix broken markdown links
```

Expected result:

- The event is ingested.
- It should not link to the decision you created in Test 1.
- It should not create a misleading decision KO.

## Chat Agent Tests

### Test 7: Known Decision Query

Ask the chat UI about the same topic you used in Test 1. Example prompts:

```text
What decisions have we made about deployment?
What did we decide about SSO?
What did we choose for error tracking?
What decisions have been made about the worker queue?
```

Expected result:

- The agent searches the knowledge base.
- It returns a real answer that references the matching decision.
- If Backboard is available, the answer should cite the KO or event.
- If Backboard is unavailable, the fallback should return raw search results instead of the generic failure message.

### Test 8: Narrow Follow-Up Query

After Test 7, ask:

```text
Why did we make that change?
```

Expected result:

- The persistent chat thread is reused.
- The answer uses the same underlying evidence, not an unrelated decision.
- If no explicit rationale exists, the answer should say the rationale was not clearly stated.

### Test 9: Service Failure Fallback

Temporarily break the Backboard configuration (for example, use an invalid API key) and ask:

```text
What decisions have we made about the queue?
```

Expected result:

- The backend logs should show the real Backboard error with traceback.
- The chat endpoint should still return a fallback answer based on direct database search when possible.
- The UI should not only show "Sorry, something went wrong while investigating."

## Correlation Merge Tests

### Test 10: Two Related Decisions Merge

Within 24 hours, send these two Slack messages:

```text
We've decided to standardize on Grafana Cloud for service dashboards.
Final decision: Grafana Cloud will be our default monitoring stack.
```

Expected result:

- Two decision KOs may be created initially.
- When `run_correlation_async()` runs, the pair should merge if their score exceeds `0.6`.
- The lower-confidence KO should be marked as `merged`.

### Test 11: Similar Time, Different Topic, No Merge

Within the same 24-hour window, send:

```text
We've decided to standardize on Grafana Cloud for service dashboards.
We've decided to move frontend deployment to Cloudflare Pages.
```

Expected result:

- Both decisions are ingested.
- They should remain separate KOs unless there is unusually strong overlapping evidence.

## Negative Tests

### Test 12: Casual Slack Messages Should Not Create KOs

Send these exact messages:

```text
Can someone review my PR?
Lunch at 12?
The staging server looks slow today.
```

Expected result:

- The pre-filter should reject them, or the classifier should mark them as non-significant.
- No KO should be created.

### Test 13: Vague Discussion Without A Decision

Send:

```text
We should probably compare Auth0 and Clerk again this week.
```

Expected result:

- This may pass the pre-filter because it is technical discussion.
- The classifier should still reject it as not yet a decision, approval, change, or blocker.
- No decision KO should be stored.

## What To Inspect After Each Test

- In the Knowledge feed, click the decision card to open the detail page, then use `Show Context` in the `Decision Context` panel to verify whether context was captured.
- Backend logs for detailed chat or Slack API errors.
- The `events` table for enriched `metadata`.
- The `knowledge_objects` table for new or merged KOs.
- The `knowledge_events` table for source-event and GitHub-evidence links.
- Chat UI output for fallback behavior and useful answers.

## Regression Checklist

1. Slack webhook still returns `{"ok": true}` quickly and does not block on long processing.
2. Existing GitHub ingestion still creates or links events normally.
3. Chat history still persists user and assistant messages.
4. No raw datetime objects appear in agent tool responses.
