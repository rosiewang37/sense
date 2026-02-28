"""Embedding generation via Backboard API (Gemini embedding, 768 dims)."""
import logging
import struct

logger = logging.getLogger(__name__)


async def generate_embedding(text: str) -> bytes | None:
    """Generate a 768-dim embedding for text and return as bytes.

    Uses the Backboard API with Gemini embedding model.
    Returns None on failure.
    """
    if not text or not text.strip():
        return None

    try:
        from app.backboard.llm import backboard_llm
        vector = await backboard_llm.embed(text)
        if vector and len(vector) > 0:
            return vector_to_bytes(vector)
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")

    return None


def vector_to_bytes(vector: list[float]) -> bytes:
    """Pack a float vector into bytes for storage."""
    return struct.pack(f"{len(vector)}f", *vector)


def bytes_to_vector(data: bytes) -> list[float]:
    """Unpack bytes back to a float vector."""
    count = len(data) // 4  # 4 bytes per float32
    return list(struct.unpack(f"{count}f", data))
