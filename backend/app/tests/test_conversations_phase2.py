import pytest
import uuid
import json
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch
from app.main import app
from app.repositories.message_repository import MessageRepository
from app.repositories.conversation_repository import ConversationRepository
from app.services.conversation.status_service import StatusService

msg_repo = MessageRepository()
conv_repo = ConversationRepository()
status_service = StatusService()


@pytest.mark.asyncio
async def test_conversations_phase2_endpoints():
    """Test all Phase 2 endpoints: status, stream, cancel, regenerate, edit, feedback, and export."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        
        # 1. Sign up and authenticate user
        signup_payload = {
            "name": "Phase2 User",
            "email": "phase2@example.com",
            "password": "securepassword123",
            "role": "user"
        }
        await ac.post("/api/v1/auth/signup", json=signup_payload)
        
        login_data = {
            "username": "phase2@example.com",
            "password": "securepassword123"
        }
        login_res = await ac.post("/api/v1/auth/login", data=login_data)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create conversation
        conv_payload = {
            "title": "Phase 2 Chat",
            "settings": {
                "model": "gemini-1.5-flash",
                "temperature": 0.7,
                "max_tokens": 1024,
                "language": "en"
            }
        }
        create_res = await ac.post("/api/v1/conversations/", json=conv_payload, headers=headers)
        assert create_res.status_code == 201
        conv_data = create_res.json()
        conv_id = conv_data["id"]

        # 3. Test Live Status Endpoint (Initial state: IDLE)
        status_res = await ac.get(f"/api/v1/conversations/{conv_id}/status", headers=headers)
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "IDLE"

        # 4. Test SSE POST Streaming Response
        stream_payload = {"content": "Hello bot"}
        
        async def mock_stream(*args, **kwargs):
            yield "Hi"
            yield " User"
            
        with patch("app.providers.gemini_provider.GeminiProvider.generate_stream", side_effect=mock_stream), \
             patch("app.providers.gemini_provider.GeminiProvider.count_tokens", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 2
            
            stream_res = await ac.post(
                f"/api/v1/conversations/{conv_id}/messages/stream",
                json=stream_payload,
                headers=headers
            )
            assert stream_res.status_code == 200
            assert "text/event-stream" in stream_res.headers["content-type"]
            body = stream_res.text
            assert "event: token" in body
            assert "event: done" in body
            assert "Hi" in body
            assert "User" in body

        # 5. Test Stop/Cancel Generation Endpoint
        cancel_res = await ac.post(f"/api/v1/conversations/{conv_id}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"

        # 6. Test Feedback endpoint (LIKE, DISLIKE, SAVE, REPORT)
        # Fetch conversation messages to get assistant message ID
        history_res = await ac.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
        assert history_res.status_code == 200
        messages = history_res.json()
        
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1
        ass_msg_id = assistant_msgs[0]["id"]
        
        # Save LIKE reaction
        feedback_payload = {"rating": "LIKE"}
        fb_res = await ac.post(f"/api/v1/messages/{ass_msg_id}/feedback", json=feedback_payload, headers=headers)
        assert fb_res.status_code == 200
        assert fb_res.json()["status"] == "saved"
        assert fb_res.json()["rating"] == "LIKE"

        # 7. Test Message Regeneration Endpoint
        with patch("app.providers.gemini_provider.GeminiProvider.generate_response", new_callable=AsyncMock) as mock_gen, \
             patch("app.providers.gemini_provider.GeminiProvider.count_tokens", new_callable=AsyncMock) as mock_tokens, \
             patch("app.services.conversation.generation_service.FastAPIBackgroundTaskQueue.enqueue") as mock_queue:
            
            mock_gen.return_value = "Regenerated content response"
            mock_tokens.return_value = 5
            
            regen_res = await ac.post(
                f"/api/v1/messages/{ass_msg_id}/regenerate",
                headers=headers
            )
            assert regen_res.status_code == 200
            regen_data = regen_res.json()
            assert regen_data["role"] == "assistant"
            assert regen_data["content"] == "Regenerated content response"
            assert regen_data["version"] == 2
            assert regen_data["retry_count"] == 1
            assert regen_data["parent_message_id"] == ass_msg_id

        # 8. Test User Message Editing Endpoint
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) >= 1
        user_msg_id = user_msgs[0]["id"]
        
        with patch("app.providers.gemini_provider.GeminiProvider.generate_response", new_callable=AsyncMock) as mock_gen, \
             patch("app.providers.gemini_provider.GeminiProvider.count_tokens", new_callable=AsyncMock) as mock_tokens, \
             patch("app.services.conversation.generation_service.FastAPIBackgroundTaskQueue.enqueue") as mock_queue:
             
            mock_gen.return_value = "Response to edited user message"
            mock_tokens.return_value = 5
            
            edit_payload = {"content": "Edited greeting"}
            edit_res = await ac.put(
                f"/api/v1/messages/{user_msg_id}",
                json=edit_payload,
                headers=headers
            )
            assert edit_res.status_code == 200
            assert edit_res.json()["content"] == "Response to edited user message"

        # 9. Test Export Endpoint
        # Text export
        exp_txt = await ac.get(f"/api/v1/conversations/{conv_id}/export?format=txt", headers=headers)
        assert exp_txt.status_code == 200
        assert "text/plain" in exp_txt.headers["content-type"]
        assert "Title:" in exp_txt.text
        
        # Markdown export
        exp_md = await ac.get(f"/api/v1/conversations/{conv_id}/export?format=markdown", headers=headers)
        assert exp_md.status_code == 200
        assert "text/markdown" in exp_md.headers["content-type"]
        assert "# Phase 2 Chat" in exp_md.text
        
        # HTML export
        exp_html = await ac.get(f"/api/v1/conversations/{conv_id}/export?format=html", headers=headers)
        assert exp_html.status_code == 200
        assert "text/html" in exp_html.headers["content-type"]
        assert "<html>" in exp_html.text

        # PDF export
        exp_pdf = await ac.get(f"/api/v1/conversations/{conv_id}/export?format=pdf", headers=headers)
        assert exp_pdf.status_code == 200
        assert "application/pdf" in exp_pdf.headers["content-type"]
        assert b"%PDF-1.4" in exp_pdf.content
