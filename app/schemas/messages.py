"""Message schemas for RIP."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class LineMessage(BaseModel):
    """LINE message model."""

    type: str
    text: Optional[str] = None
    id: Optional[str] = None


class LineEvent(BaseModel):
    """LINE event model."""

    type: str
    message: LineMessage
    timestamp: int
    mode: str = "active"
    replyToken: str
    source: dict[str, Any] = Field(default_factory=dict)


class LineWebhookRequest(BaseModel):
    """LINE webhook request model."""

    events: list[LineEvent]
    destination: str = ""


class WorkerRequest(BaseModel):
    """Worker request model."""

    worker_id: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    user_id: str
    request_id: str


class WorkerResponse(BaseModel):
    """Worker response model."""

    success: bool
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    worker_id: str
    execution_time_ms: float
