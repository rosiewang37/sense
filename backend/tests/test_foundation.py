"""Phase 1 tests: Foundation & Infrastructure.

Tests:
- Health check endpoint
- Database connectivity
- Background task execution
- Auth: register → login → access protected route
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient


# --- Health Check ---

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """GET /health returns 200 with status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "Sense"


# --- Database Connection ---

@pytest.mark.asyncio
async def test_db_connection(client: AsyncClient):
    """GET /health/db confirms database is reachable."""
    response = await client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


# --- Background Task ---

@pytest.mark.asyncio
async def test_background_task():
    """Background ping task returns 'pong'."""
    from app.sense.tasks import ping

    result = await ping()
    assert result == "pong"


# --- Auth: Register → Login → Protected Route ---

@pytest.mark.asyncio
async def test_auth_register_login(client: AsyncClient):
    """Register a user, login, and access /api/auth/me."""
    # 1. Register
    register_resp = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "name": "Test User",
        "password": "securepassword123",
    })
    assert register_resp.status_code == 200
    token_data = register_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 2. Login with same credentials
    login_resp = await client.post(
        "/api/auth/login",
        data={"username": "test@example.com", "password": "securepassword123"},
    )
    assert login_resp.status_code == 200
    login_token = login_resp.json()
    assert "access_token" in login_token

    # 3. Access protected route
    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_token['access_token']}"},
    )
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert user_data["email"] == "test@example.com"
    assert user_data["name"] == "Test User"


@pytest.mark.asyncio
async def test_auth_duplicate_register(client: AsyncClient):
    """Registering the same email twice should fail."""
    await client.post("/api/auth/register", json={
        "email": "duplicate@example.com",
        "name": "First User",
        "password": "password123",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "duplicate@example.com",
        "name": "Second User",
        "password": "password456",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_auth_bad_login(client: AsyncClient):
    """Login with wrong password should fail."""
    resp = await client.post(
        "/api/auth/login",
        data={"username": "nonexistent@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_protected_no_token(client: AsyncClient):
    """Accessing protected route without token should fail."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
