import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_signup():
    """Verify signup creates a new user profile and redirects properly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        signup_payload = {
            "name": "Test User",
            "email": "testuser@example.com",
            "password": "securepassword123",
            "role": "user"
        }
        response = await ac.post("/api/v1/auth/signup", json=signup_payload)
        
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["name"] == "Test User"
    assert "id" in data
    assert data["role"] == "admin"  # First user in DB gets admin auto-role


@pytest.mark.asyncio
async def test_login():
    """Verify credentials validation and token issuance."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Sign up user first
        signup_payload = {
            "name": "Login User",
            "email": "loginuser@example.com",
            "password": "securepassword123",
            "role": "user"
        }
        await ac.post("/api/v1/auth/signup", json=signup_payload)

        # Attempt login
        login_payload = {
            "username": "loginuser@example.com",
            "password": "securepassword123"
        }
        response = await ac.post("/api/v1/auth/login", data=login_payload)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials():
    """Verify invalid password returns error status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login_payload = {
            "username": "nonexistent@example.com",
            "password": "wrongpassword"
        }
        response = await ac.post("/api/v1/auth/login", data=login_payload)

    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_read_users_me():
    """Verify access token allows retrieval of profile metadata."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Sign up
        signup_payload = {
            "name": "Me User",
            "email": "meuser@example.com",
            "password": "securepassword123",
            "role": "user"
        }
        await ac.post("/api/v1/auth/signup", json=signup_payload)

        # Login
        login_payload = {
            "username": "meuser@example.com",
            "password": "securepassword123"
        }
        login_res = await ac.post("/api/v1/auth/login", data=login_payload)
        token = login_res.json()["access_token"]

        # Access /me endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = await ac.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "meuser@example.com"
    assert data["name"] == "Me User"
