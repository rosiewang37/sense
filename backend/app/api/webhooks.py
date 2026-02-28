"""Webhook receivers for Slack and GitHub."""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import get_settings
from app.sense.integrations.slack import parse_slack_event, verify_slack_signature
from app.sense.integrations.github import parse_github_event, verify_github_signature
from app.sense.tasks import process_event_async

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/slack")
async def slack_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Slack Events API webhooks."""
    body = await request.body()
    logger.info(f"Slack webhook received: {len(body)} bytes")

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Slack webhook: invalid JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle Slack URL verification challenge
    if payload.get("type") == "url_verification":
        logger.info("Slack URL verification challenge received")
        return {"challenge": payload["challenge"]}

    # Verify signature if signing secret is configured
    if settings.slack_signing_secret:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        if not verify_slack_signature(body, timestamp, signature, settings.slack_signing_secret):
            logger.warning("Slack webhook: signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Parse event and dispatch to background processing
    event_data = parse_slack_event(payload)
    background_tasks.add_task(process_event_async, event_data)
    logger.info(f"Dispatched Slack event {event_data.get('source_id')} to background")

    return {"ok": True}


@router.post("/slack/event")
@router.post("/slack/events")
async def slack_webhook_alt(request: Request, background_tasks: BackgroundTasks):
    """Catch alternate Slack webhook paths and redirect to main handler."""
    logger.info("Slack webhook hit on alternate path, forwarding to main handler")
    return await slack_webhook(request, background_tasks)


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default="ping"),
    x_hub_signature_256: str = Header(default=""),
):
    """Receive GitHub webhooks."""
    body = await request.body()

    # Verify signature if webhook secret is configured
    if settings.github_webhook_secret and x_hub_signature_256:
        if not verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    if x_github_event == "ping":
        return {"ok": True}

    payload = await request.json()
    events = parse_github_event(x_github_event, payload)

    for event_data in events:
        background_tasks.add_task(process_event_async, event_data)
        logger.info(f"Dispatched GitHub event {event_data.get('source_id')} to background")

    return {"ok": True}
