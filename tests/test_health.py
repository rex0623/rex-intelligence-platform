"""Health check tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "application" in data
    assert "version" in data


def test_health_check_detailed(client):
    """Test detailed health check endpoint."""
    response = client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "router" in data


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "endpoints" in data


def test_line_webhook_invalid_signature(client):
    """Test LINE webhook with invalid signature."""
    response = client.post(
        "/line/webhook",
        json={"events": []},
        headers={"X-Line-Signature": "invalid_signature"},
    )

    assert response.status_code == 401


def test_line_webhook_no_signature(client):
    """Test LINE webhook without signature header."""
    response = client.post(
        "/line/webhook",
        json={
            "events": [
                {
                    "type": "message",
                    "message": {
                        "type": "text",
                        "text": "Hello",
                        "id": "1234567890",
                    },
                    "timestamp": 1234567890,
                    "mode": "active",
                    "replyToken": "test_token",
                    "source": {"type": "user", "userId": "test_user"},
                }
            ]
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "Missing X-Line-Signature header"


def test_line_webhook_invalid_json(client):
    """Test LINE webhook with invalid JSON."""
    response = client.post(
        "/line/webhook",
        content="invalid json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_line_webhook_text_message_replies_fixed_text(client, monkeypatch):
    """Test LINE webhook text message replies with fixed response."""
    reply_called = {}

    def fake_verify_signature(signature, body):
        reply_called["verified"] = True
        return True

    def fake_reply_text(reply_token, text):
        reply_called["reply_token"] = reply_token
        reply_called["text"] = text
        return {"status": "dry_run", "reply_token": reply_token, "message": text}

    monkeypatch.setattr("app.main.line_gateway.verify_signature", fake_verify_signature)
    monkeypatch.setattr("app.main.line_gateway.reply_text", fake_reply_text)

    response = client.post(
        "/line/webhook",
        json={
            "events": [
                {
                    "type": "message",
                    "message": {
                        "type": "text",
                        "text": "Hello from LINE",
                        "id": "1234567890",
                    },
                    "timestamp": 1234567890,
                    "mode": "active",
                    "replyToken": "test_token",
                    "source": {"type": "user", "userId": "test_user"},
                }
            ]
        },
        headers={"X-Line-Signature": "test_signature"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert reply_called["verified"] is True
    assert reply_called["reply_token"] == "test_token"
    assert reply_called["text"] == "收到，我是小雷。你剛剛說：Hello from LINE"
    assert data["details"]["results"][0]["reply"]["status"] == "dry_run"
