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
