"""Health check tests."""

import pytest
from pathlib import Path
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


@pytest.mark.parametrize(
    "text, expected_worker, expected_reply",
    [
        ("請幫我看電費單", "pdf_worker", "小雷收到：我判斷這是 PDF 任務"),
        ("請幫我整理 Downloads", "folder_worker", "小雷收到：我判斷這是資料夾整理任務"),
        ("幫我寫 API", "claude_worker", "小雷收到：我判斷這是程式開發任務"),
        ("幫我整理需求", "gpt_worker", "小雷收到：我判斷這是需求分析任務"),
        ("你好", "default", "小雷收到：我還不確定你的需求，可以再說清楚一點嗎？"),
    ],
)
def test_line_webhook_text_message_routing(client, monkeypatch, text, expected_worker, expected_reply):
    """Test LINE webhook text message routing for different intents."""
    if expected_worker == "folder_worker":
        safe_root = Path("/tmp/safe_root")
        downloads = safe_root / "Downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("app.core.config.settings.SAFE_FOLDER_ROOT", str(safe_root))
        # Patch the already-initialized ai_router's FolderWorker instance
        try:
            import app.main as main_app

            main_app.ai_router.workers["folder_worker"].safe_root = safe_root.resolve()
        except Exception:
            pass
    reply_called = {}

    def fake_verify_signature(signature, body):
        reply_called["verified"] = True
        return True

    def fake_reply_text(reply_token, reply_text):
        reply_called["reply_token"] = reply_token
        reply_called["text"] = reply_text
        return {"status": "dry_run", "reply_token": reply_token, "message": reply_text}

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
                        "text": text,
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
    if expected_worker == "folder_worker":
        assert reply_called["text"].startswith("小雷收到：資料夾分析完成")
        assert "dry-run 模式" in reply_called["text"]
    elif expected_worker == "pdf_worker":
        assert reply_called["text"].startswith("小雷收到：已建立電費單處理流程（dry-run）")
        assert "狀態：waiting_approval" in reply_called["text"]
        assert "步驟：" in reply_called["text"]
    else:
        assert reply_called["text"] == expected_reply
    assert data["details"]["results"][0]["reply"]["status"] == "dry_run"
    assert data["details"]["results"][0]["worker_id"] == expected_worker
