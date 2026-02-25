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

# Model mapping
MODELS = {
    "detection": {"provider": "google", "model": "gemini-2.0-flash"},
    "extraction": {"provider": "google", "model": "gemini-2.0-flash"},
    "verification": {"provider": "google", "model": "gemini-2.0-flash"},
    "chat": {"provider": "google", "model": "gemini-2.5-pro"},
    "embedding": {"provider": "google", "model": "text-embedding-004"},
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

        Returns a 768-dimensional vector.
        """
        model_config = MODELS["embedding"]
        assistant_id = await self._get_or_create_assistant("embedding")

        async with httpx.AsyncClient(timeout=30.0) as client:
            thread_resp = await client.post(
                f"{BACKBOARD_BASE}/assistants/{assistant_id}/threads",
                headers=self._headers(),
                json={},
            )
            thread_resp.raise_for_status()
            thread_id = thread_resp.json()["thread_id"]

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
            # The embedding should be returned in the response
            return result.get("embedding", [0.0] * 768)

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
            payload["embedding_model_name"] = "text-embedding-004"
            payload["embedding_dims"] = 768

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
