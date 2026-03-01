"""Slack Web API helpers for enriching ingested Slack events."""
import logging

import httpx

SLACK_API_BASE = "https://slack.com/api"
USER_NAME_CACHE: dict[str, str] = {}

logger = logging.getLogger(__name__)


async def _slack_get(endpoint: str, bot_token: str, params: dict) -> dict | None:
    """Call a Slack Web API GET endpoint and return the parsed JSON body."""
    if not bot_token:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SLACK_API_BASE}/{endpoint}",
                headers={"Authorization": f"Bearer {bot_token}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Slack API request failed for %s: %s", endpoint, exc)
        return None

    if not data.get("ok", False):
        logger.warning(
            "Slack API returned an error for %s: %s",
            endpoint,
            data.get("error", "unknown_error"),
        )
        return None

    return data


async def resolve_user_name(user_id: str, bot_token: str) -> str:
    """Resolve a Slack user ID to a display name, with a simple in-memory cache."""
    if not user_id:
        return ""
    if user_id in USER_NAME_CACHE:
        return USER_NAME_CACHE[user_id]

    # If it does not look like a Slack user ID, treat it as already human-readable.
    if not user_id.startswith(("U", "W")):
        USER_NAME_CACHE[user_id] = user_id
        return user_id

    data = await _slack_get("users.info", bot_token, {"user": user_id})
    if not data:
        return user_id

    user = data.get("user") or {}
    profile = user.get("profile") or {}
    display_name = (
        profile.get("display_name")
        or profile.get("real_name")
        or user.get("real_name")
        or user.get("name")
        or user_id
    )
    USER_NAME_CACHE[user_id] = display_name
    return display_name


async def fetch_surrounding_messages(
    channel: str,
    message_ts: str,
    bot_token: str,
    window: int = 3,
) -> list[dict]:
    """Fetch a best-effort slice of nearby channel messages around a message timestamp."""
    if not channel or not message_ts or not bot_token:
        return []

    before_data = await _slack_get(
        "conversations.history",
        bot_token,
        {
            "channel": channel,
            "latest": message_ts,
            "inclusive": "true",
            "limit": max(1, window + 1),
        },
    )
    after_data = await _slack_get(
        "conversations.history",
        bot_token,
        {
            "channel": channel,
            "oldest": message_ts,
            "inclusive": "false",
            "limit": max(1, window),
        },
    )

    raw_messages: dict[str, dict] = {}
    for payload in (before_data, after_data):
        for message in (payload or {}).get("messages", []):
            ts = str(message.get("ts") or "")
            if ts and ts not in raw_messages:
                raw_messages[ts] = message

    if not raw_messages:
        return []

    ordered = sorted(raw_messages.values(), key=lambda item: float(item.get("ts", 0) or 0))
    trigger_index = next(
        (index for index, item in enumerate(ordered) if str(item.get("ts") or "") == message_ts),
        None,
    )

    if trigger_index is not None:
        start = max(0, trigger_index - window)
        end = min(len(ordered), trigger_index + window + 1)
        ordered = ordered[start:end]

    enriched = []
    for message in ordered:
        user_name = await resolve_user_name(
            str(message.get("user") or message.get("bot_id") or message.get("username") or ""),
            bot_token,
        )
        enriched.append(
            {
                "user_name": user_name or "Unknown",
                "text": message.get("text", "") or "",
                "ts": str(message.get("ts") or ""),
            }
        )

    return enriched


async def get_file_metadata(file_id: str, bot_token: str) -> dict | None:
    """Fetch basic metadata for a Slack file attachment."""
    if not file_id or not bot_token:
        return None

    data = await _slack_get("files.info", bot_token, {"file": file_id})
    if not data:
        return None

    file_data = data.get("file") or {}
    return {
        "id": str(file_data.get("id") or file_id),
        "name": file_data.get("name", "") or "",
        "filetype": file_data.get("filetype", "") or "",
        "mimetype": file_data.get("mimetype", "") or "",
        "url_private": file_data.get("url_private", "") or "",
        "permalink": file_data.get("permalink", "") or "",
    }
