"""Backboard API LLM gateway client.

All LLM calls (classification, extraction, agents, embeddings) go through this module.
Wraps the Backboard API to provide chat, function calling, and embedding generation.
"""
import json
import httpx
from app.config import get_settings

settings = get_settings()

BACKBOARD_BASE = settings.backboard_api_url
BACKBOARD_KEY = settings.backboard_api_key

# Model mapping — uses models available on the Backboard instance
MODELS = {
    "detection": {"provider": "anthropic", "model": "claude-3-haiku-20240307"},
    "extraction": {"provider": "anthropic", "model": "claude-3-haiku-20240307"},
    "verification": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "chat": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "embedding": {"provider": "cohere", "model": "embed-english-v3.0"},
}


class BackboardLLMClient:
    """Client for the Backboard API LLM gateway."""

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
        async with httpx.AsyncClient(timeout=60.0) as client:
            thread_resp = await client.post(
                f"{BACKBOARD_BASE}/assistants/{assistant_id}/threads",
                headers=self._headers(),
                json={},
            )
            thread_resp.raise_for_status()
            thread_id = thread_resp.json()["thread_id"]

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

        Backboard API does not expose a standalone embedding endpoint — embeddings
        are used internally for RAG/memory. This method returns an empty list to
        signal that embedding generation is unavailable. The calling code in
        embeddings.py already handles this gracefully (returns None).
        """
        return []

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
            payload["embedding_provider"] = "cohere"
            payload["embedding_model_name"] = "embed-english-v3.0"
            payload["embedding_dims"] = 1024

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{BACKBOARD_BASE}/assistants",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            assistant_id = resp.json()["assistant_id"]
            self._assistants[role] = assistant_id
            return assistant_id


# Singleton client instance
backboard_llm = BackboardLLMClient()
