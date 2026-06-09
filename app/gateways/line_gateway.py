"""LINE Gateway for RIP."""

import base64
import hashlib
import hmac
from typing import Any, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.router.ai_router import AIRouter
from app.schemas.messages import LineEvent, LineWebhookRequest

logger = get_logger(__name__)


class LineGateway:
    """LINE Gateway - Handle LINE messages and route to AI Router."""

    def __init__(self, router: Optional[AIRouter] = None):
        """
        Initialize LINE gateway.

        Args:
            router: AI Router instance
        """
        self.router = router or AIRouter()
        self.line_bot_api = None

    def verify_signature(self, signature: str, body: str) -> bool:
        """
        Verify LINE webhook signature.

        Args:
            signature: X-Line-Signature header value
            body: Request body

        Returns:
            True if signature is valid
        """
        if not signature:
            logger.warning("Missing X-Line-Signature header")
            return False

        channel_secret = settings.LINE_CHANNEL_SECRET
        if not channel_secret:
            logger.warning("LINE_CHANNEL_SECRET not set, cannot verify signature")
            return False

        expected_signature = hmac.new(
            channel_secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).digest()

        expected_signature_b64 = base64.b64encode(expected_signature).decode()

        return signature == expected_signature_b64

    def reply_text(self, reply_token: str, text: str) -> dict[str, Any]:
        """
        Reply to a LINE text message.

        Args:
            reply_token: LINE reply token
            text: Reply text content

        Returns:
            Result data from send or dry run
        """
        logger.info(
            "Replying to LINE text message",
            extra={"reply_token": reply_token, "text": text},
        )

        if not reply_token:
            logger.warning("Missing reply token for LINE reply")
            return {"status": "failed", "reason": "missing_reply_token"}

        if not settings.LINE_ACCESS_TOKEN:
            logger.info("Dry run reply: LINE_ACCESS_TOKEN not configured")
            return {"status": "dry_run", "reply_token": reply_token, "message": text}

        try:
            from linebot import LineBotApi
            from linebot.exceptions import LineBotApiError
            from linebot.models import TextSendMessage
        except ImportError:
            logger.warning("LINE SDK not installed, using dry run reply")
            return {"status": "dry_run", "reply_token": reply_token, "message": text}

        try:
            line_bot_api = LineBotApi(settings.LINE_ACCESS_TOKEN)
            line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
            return {"status": "success", "reply_token": reply_token, "message": text}
        except LineBotApiError as e:
            logger.error("LINE API reply failed", exc_info=True)
            return {"status": "failed", "reason": str(e)}

    async def handle_webhook(
        self,
        request: LineWebhookRequest,
        user_id: str = None,
    ) -> dict[str, Any]:
        """
        Handle LINE webhook request.

        Args:
            request: LINE webhook request
            user_id: User ID (from verified request)

        Returns:
            Response data
        """
        logger.info(
            "LINE Gateway received webhook",
            extra={"events_count": len(request.events)},
        )

        results = []

        for event in request.events:
            if event.type == "message" and event.message.type == "text":
                router_result = await self.router.route(
                    user_id=user_id or event.source.get("userId", "unknown"),
                    message=event.message.text,
                    metadata={
                        "line_event_id": event.message.id,
                        "reply_token": event.replyToken,
                    },
                )

                reply_payload = self.reply_text(
                    event.replyToken,
                    f"收到，我是小雷。你剛剛說：{event.message.text}",
                )

                results.append(
                    {
                        "event_type": event.type,
                        "user_id": event.source.get("userId", "unknown"),
                        "message": event.message.text,
                        "intent": router_result.get("intent"),
                        "worker_id": router_result.get("worker_id"),
                        "reply": reply_payload,
                    }
                )
            else:
                logger.debug(f"Ignoring event type: {event.type}")

        return {
            "status": "success",
            "events_processed": len(results),
            "results": results,
        }

    async def _handle_text_message(
        self,
        event: LineEvent,
        user_id: str = None,
    ) -> dict[str, Any]:
        """
        Handle text message from LINE.

        Args:
            event: LINE event
            user_id: User ID

        Returns:
            Handler result
        """
        message_text = event.message.text
        user_id = user_id or event.source.get("userId", "unknown")

        logger.info(
            "Handling text message",
            extra={"user_id": user_id, "message": message_text},
        )

        # Route message through AI Router
        router_result = await self.router.route(
            user_id=user_id,
            message=message_text,
            metadata={
                "line_event_id": event.message.id,
                "reply_token": event.replyToken,
            },
        )

        logger.info(
            "Message routed",
            extra={
                "user_id": user_id,
                "worker_id": router_result.get("worker_id"),
            },
        )

        return {
            "user_id": user_id,
            "message": message_text,
            "intent": router_result.get("intent"),
            "worker_id": router_result.get("worker_id"),
            "response": router_result.get("response"),
        }

    async def send_reply(self, reply_token: str, messages: list[dict]) -> bool:
        """
        Send reply message to LINE user.

        Args:
            reply_token: LINE reply token
            messages: Message list to send

        Returns:
            True if successful
        """
        logger.info(
            "Sending reply to LINE",
            extra={"message_count": len(messages)},
        )

        # Phase 1: Just log, don't actually send
        # Implementation will be done in Phase 2 with actual LINE API integration

        return True
