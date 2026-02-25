"""Integration management API — implemented in Phase 2."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
