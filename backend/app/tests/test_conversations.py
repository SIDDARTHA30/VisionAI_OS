import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest.mark.asyncio
async def test_conversation_flow():
    """Verify complete CRUD flow and AI message processing with patched provider responses."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        
        # 1. Sign up and authenticate user
        signup_payload = {
            "name": "Test Chat User",
            "email": "chatuser@example.com",
            "password": "chatpassword123",
            "role": "user"
        }
        signup_res = await ac.post("/api/v1/auth/signup", json=signup_payload)
        assert signup_res.status_code == 201
        
        login_data = {
            "username": "chatuser@example.com",
            "password": "chatpassword123"
        }
        login_res = await ac.post("/api/v1/auth/login", data=login_data)
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Block request if authorization header is missing
        blocked_res = await ac.post("/api/v1/conversations/", json={"title": "Unauthorized Chat"})
        assert blocked_res.status_code == 401

        # 3. Create Conversation
        conv_payload = {
            "title": "Initial AI Discussion",
            "settings": {
                "model": "gemini-1.5-flash",
                "temperature": 0.5,
                "max_tokens": 1024,
                "language": "en",
                "system_prompt": "chat",
                "stream_enabled": False
            }
        }
        create_res = await ac.post("/api/v1/conversations/", json=conv_payload, headers=headers)
        assert create_res.status_code == 201
        conv_data = create_res.json()
        assert conv_data["title"] == "Initial AI Discussion"
        assert conv_data["settings"]["temperature"] == 0.5
        conv_id = conv_data["id"]

        # 4. List Active Conversations
        list_res = await ac.get("/api/v1/conversations/", headers=headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1
        assert list_res.json()[0]["id"] == conv_id

        # 5. Send User Message & mock LLM completion response
        message_payload = {"content": "Explain async design patterns."}
        
        with patch("app.providers.gemini_provider.GeminiProvider.generate_response", new_callable=AsyncMock) as mock_gen, \
             patch("app.providers.gemini_provider.GeminiProvider.count_tokens", new_callable=AsyncMock) as mock_tokens, \
             patch("app.services.conversation.generation_service.FastAPIBackgroundTaskQueue.enqueue") as mock_queue:
            
            mock_gen.return_value = "Asynchronous design patterns allow non-blocking tasks."
            mock_tokens.return_value = 10
            
            send_res = await ac.post(
                f"/api/v1/conversations/{conv_id}/messages", 
                json=message_payload, 
                headers=headers
            )
            assert send_res.status_code == 201
            msg_data = send_res.json()
            assert msg_data["role"] == "assistant"
            assert msg_data["content"] == "Asynchronous design patterns allow non-blocking tasks."
            assert msg_data["status"] == "COMPLETED"

        # 6. Retrieve Conversation Message History
        history_res = await ac.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
        assert history_res.status_code == 200
        history_data = history_res.json()
        # We expect 2 messages: 1 user + 1 assistant
        assert len(history_data) == 2
        assert history_data[0]["role"] == "user"
        assert history_data[0]["content"] == "Explain async design patterns."
        assert history_data[1]["role"] == "assistant"

        # 7. Rename Conversation
        rename_payload = {"title": "Updated Programming Chat"}
        rename_res = await ac.put(f"/api/v1/conversations/{conv_id}", json=rename_payload, headers=headers)
        assert rename_res.status_code == 200
        assert rename_res.json()["title"] == "Updated Programming Chat"

        # 8. Soft Delete Conversation
        del_res = await ac.delete(f"/api/v1/conversations/{conv_id}", headers=headers)
        assert del_res.status_code == 204

        # 9. Verify deleted conversation does not appear in listing
        list_after_res = await ac.get("/api/v1/conversations/", headers=headers)
        assert list_after_res.status_code == 200
        assert conv_id not in [c["id"] for c in list_after_res.json()]


@pytest.mark.asyncio
async def test_ai_health_check():
    """Verify that the AI health check endpoint resolves correctly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.providers.gemini_provider.GeminiProvider.count_tokens", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 5
            response = await ac.get("/api/v1/health/ai")
            assert response.status_code == 200
            data = response.json()
            assert data["provider"] == "gemini"
            assert data["status"] == "healthy"
            assert "latency_ms" in data


@pytest.mark.asyncio
async def test_concurrent_message_locks():
    """Verify that concurrent message submissions are blocked by the Redis lock."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/v1/auth/signup",
            json={"name": "Lock User", "email": "lock@example.com", "password": "password123", "role": "user"}
        )
        login_res = await ac.post(
            "/api/v1/auth/login",
            data={"username": "lock@example.com", "password": "password123"}
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create conversation
        conv_res = await ac.post(
            "/api/v1/conversations/",
            json={"title": "Lock Test Chat"},
            headers=headers
        )
        conv_id = conv_res.json()["id"]
        
        # Mock redis_client to return None (meaning lock acquisition failed/conflict)
        with patch("app.services.conversation.generation_service.redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.set.return_value = None
            
            # Posting a message must be rejected immediately with 409 Conflict
            res = await ac.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Msg 1"},
                headers=headers
            )
            assert res.status_code == 409
            assert "already being generated" in res.json()["detail"]
            mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_redis_unavailable_fallback():
    """Verify that the application falls back gracefully if Redis is offline/unreachable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/v1/auth/signup",
            json={"name": "Fallback User", "email": "fallback@example.com", "password": "password123", "role": "user"}
        )
        login_res = await ac.post(
            "/api/v1/auth/login",
            data={"username": "fallback@example.com", "password": "password123"}
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create conversation
        conv_res = await ac.post(
            "/api/v1/conversations/",
            json={"title": "Fallback Test Chat"},
            headers=headers
        )
        conv_id = conv_res.json()["id"]
        
        # Mock redis_client to raise a ConnectionError (simulating Redis offline)
        from redis.exceptions import ConnectionError as RedisConnectionError
        with patch("app.services.conversation.generation_service.redis_client", new_callable=AsyncMock) as mock_redis, \
             patch("app.providers.gemini_provider.GeminiProvider.generate_response", new_callable=AsyncMock) as mock_gen, \
             patch("app.providers.gemini_provider.GeminiProvider.count_tokens", new_callable=AsyncMock) as mock_tokens, \
             patch("app.services.conversation.generation_service.FastAPIBackgroundTaskQueue.enqueue") as mock_queue:
             
            mock_redis.set.side_effect = RedisConnectionError("Redis connection down")
            mock_gen.return_value = "Fallback response"
            mock_tokens.return_value = 5
            
            # The message submission must proceed and return 201 Created
            res = await ac.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"content": "Msg 1"},
                headers=headers
            )
            assert res.status_code == 201
            assert res.json()["content"] == "Fallback response"
            assert res.json()["status"] == "COMPLETED"
