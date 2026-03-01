"""Backboard API LLM gateway client.

All LLM calls (classification, extraction, agents, embeddings) go through this module.
Wraps the Backboard API to provide chat, function calling, and embedding generation.
"""
import json
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

BACKBOARD_BASE = settings.backboard_api_url
BACKBOARD_KEY = settings.backboard_api_key

# Model mapping — uses Gemini models via Backboard
MODELS = {
    "detection": {"provider": "google", "model": "gemini-2.0-flash-lite-001"},
    "extraction": {"provider": "google", "model": "gemini-2.0-flash-001"},
    "verification": {"provider": "google", "model": "gemini-2.0-flash-001"},
    "chat": {"provider": "google", "model": "gemini-2.5-pro"},
    "embedding": {"provider": "google", "model": "gemini-embedding-001-768"},
}


class BackboardLLMClient:
    """Client for the Backboard API LLM gateway."""

    # Expose for use by agent modules
    MODELS = MODELS
    BACKBOARD_BASE = BACKBOARD_BASE

    def __init__(self):
        self._assistants: dict[str, str] = {}  # role -> assistant_id
        self._threads: dict[str, str] = {}  # key -> thread_id

    def _headers(self) -> dict:
        return {"X-API-Key": BACKBOARD_KEY}

    async def chat(
        self,
        messages: list[dict],
        model_role: str = "detection",
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 2048,
    ) -> dict:
        """Send a chat completion request through Backboard API.

        Returns dict with keys: content, status, tool_calls, run_id
        """
        model_config = MODELS.get(model_role, MODELS["detection"])

        # Get or create assistant for this role
        assistant_id = await self._get_or_create_assistant(
            model_role, system, tools
        )

        # Create a new thread for this conversation
        thread_id = await self.create_thread(assistant_id)

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Send the last user message
            user_msg = messages[-1]["content"] if messages else ""
            msg_resp = await client.post(
                f"{BACKBOARD_BASE}/threads/{thread_id}/messages",
                headers=self._headers(),
                data={
                    "content": user_msg,
                    "llm_provider": model_config["provider"],
                    "model_name": model_config["model"],
                    "stream": "false",
                },
            )
            msg_resp.raise_for_status()
            result = msg_resp.json()

            return {
                "content": result.get("content", ""),
                "status": result.get("status", "COMPLETED"),
                "tool_calls": result.get("tool_calls", []),
                "run_id": result.get("run_id"),
                "thread_id": thread_id,
            }

    async def create_thread(self, assistant_id: str) -> str:
        """Create a new persistent Backboard thread. Returns thread_id."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{BACKBOARD_BASE}/assistants/{assistant_id}/threads",
                    headers=self._headers(),
                    json={},
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.error(
                    "create_thread failed for assistant %s",
                    assistant_id,
                    exc_info=True,
                )
                raise
            data = resp.json()
            if "thread_id" not in data:
                logger.error(f"create_thread: response missing 'thread_id': {data}")
                raise ValueError(f"Backboard API returned unexpected response: missing 'thread_id'")
            return data["thread_id"]

    async def submit_tool_outputs(
        self, thread_id: str, run_id: str, tool_outputs: list[dict]
    ) -> dict:
        """Submit tool call results back to the model."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{BACKBOARD_BASE}/threads/{thread_id}/runs/{run_id}/submit-tool-outputs",
                headers=self._headers(),
                json={"tool_outputs": tool_outputs},
            )
            resp.raise_for_status()
            result = resp.json()
            return {
                "content": result.get("content", ""),
                "status": result.get("status", "COMPLETED"),
                "tool_calls": result.get("tool_calls", []),
                "run_id": result.get("run_id"),
            }

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        Returns a 768-dimensional vector via Gemini embedding model.
        """
        model_config = MODELS["embedding"]
        assistant_id = await self._get_or_create_assistant("embedding")
        thread_id = await self.create_thread(assistant_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            msg_resp = await client.post(
                f"{BACKBOARD_BASE}/threads/{thread_id}/messages",
                headers=self._headers(),
                data={
                    "content": text,
                    "llm_provider": model_config["provider"],
                    "model_name": model_config["model"],
                    "stream": "false",
                    "send_to_llm": "true",
                },
            )
            msg_resp.raise_for_status()
            result = msg_resp.json()
            return result.get("embedding", [])

    async def _get_or_create_assistant(
        self, role: str, system: str | None = None, tools: list[dict] | None = None
    ) -> str:
        """Get or create a Backboard assistant for the given role."""
        if role in self._assistants:
            return self._assistants[role]

        model_config = MODELS.get(role, MODELS["detection"])
        payload = {
            "name": f"sense-{role}",
        }
        if system:
            payload["system_prompt"] = system
        if tools:
            payload["tools"] = tools
        if role == "embedding":
            payload["embedding_provider"] = "google"
            payload["embedding_model_name"] = "gemini-embedding-001-768"
            payload["embedding_dims"] = 768

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{BACKBOARD_BASE}/assistants",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.error(
                    "_get_or_create_assistant failed for role %s",
                    role,
                    exc_info=True,
                )
                raise
            data = resp.json()
            if "assistant_id" not in data:
                logger.error(f"_get_or_create_assistant({role}): response missing 'assistant_id': {data}")
                raise ValueError(f"Backboard API returned unexpected response: missing 'assistant_id'")
            assistant_id = data["assistant_id"]
            logger.info(f"Created Backboard assistant for role '{role}': {assistant_id}")
            self._assistants[role] = assistant_id
            return assistant_id


# Singleton client instance
backboard_llm = BackboardLLMClient()
