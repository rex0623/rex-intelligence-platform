"""AI Router for RIP - The Brain of the System."""

import uuid
from typing import Any

from app.core.logger import get_logger
from app.schemas.messages import WorkerRequest
from app.workers import ClaudeWorker, FolderWorker, GPTWorker, PDFWorker

logger = get_logger(__name__)


class AIRouter:
    """AI Router - Intelligent message routing and task orchestration."""

    def __init__(self):
        """Initialize AI Router."""
        self.workers = {
            "pdf_worker": PDFWorker(),
            "folder_worker": FolderWorker(),
            "claude_worker": ClaudeWorker(),
            "gpt_worker": GPTWorker(),
        }

        logger.info(
            "AI Router initialized with workers",
            extra={"workers": list(self.workers.keys())},
        )

    async def route(
        self,
        user_id: str,
        message: str,
        metadata: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        Route message to appropriate worker.

        Args:
            user_id: User ID
            message: User message
            metadata: Additional metadata

        Returns:
            Router result with response
        """
        if metadata is None:
            metadata = {}

        logger.info(
            f"Router received message from user",
            extra={"user_id": user_id, "message_length": len(message)},
        )

        # Detect intent
        intent = self._detect_intent(message)
        logger.info(
            "Intent detected",
            extra={"user_id": user_id, "intent": intent},
        )

        # Select worker based on intent
        worker_id = self._select_worker(intent)
        logger.info(
            "Worker selected",
            extra={"user_id": user_id, "worker_id": worker_id},
        )

        # Create worker request
        request = WorkerRequest(
            worker_id=worker_id,
            action="generate" if worker_id.endswith("worker") else "process",
            payload={"content": message, **metadata},
            user_id=user_id,
            request_id=str(uuid.uuid4()),
        )

        # Execute worker
        if worker_id in self.workers:
            worker = self.workers[worker_id]
            response = await worker.execute(request)

            return {
                "status": "success",
                "user_id": user_id,
                "intent": intent,
                "worker_id": worker_id,
                "response": response.model_dump(),
            }

        # No matching worker
        return {
            "status": "success",
            "user_id": user_id,
            "intent": intent,
            "worker_id": None,
            "response": {
                "message": "抱歉，我不太理解您的需求。"
                "請試試以下方式："
                "\n1. 上傳 PDF：說『分析我的電費單』"
                "\n2. 整理檔案：說『整理我的資料夾』"
                "\n3. 寫程式：說『幫我寫 Python 代碼』"
            },
        }

    def _detect_intent(self, message: str) -> str:
        """
        Detect user intent from message.

        Args:
            message: User message

        Returns:
            Intent string
        """
        message_lower = message.lower()

        # PDF intent
        if any(word in message_lower for word in ["pdf", "電費單", "文件", "document"]):
            return "pdf_processing"

        # Folder intent
        if any(word in message_lower for word in ["整理", "folder", "文件夾", "資料夾"]):
            return "file_management"

        # Code generation intent
        if any(
            word in message_lower
            for word in ["寫程式", "code", "代碼", "python", "function", "函數"]
        ):
            return "code_generation"

        return "general_query"

    def _select_worker(self, intent: str) -> str:
        """
        Select worker based on intent.

        Args:
            intent: Detected intent

        Returns:
            Worker ID
        """
        intent_map = {
            "pdf_processing": "pdf_worker",
            "file_management": "folder_worker",
            "code_generation": "claude_worker",
        }

        return intent_map.get(intent, "claude_worker")

    async def get_health(self) -> dict[str, Any]:
        """
        Get router and workers health status.

        Returns:
            Health status
        """
        worker_health = {}
        for worker_id, worker in self.workers.items():
            worker_health[worker_id] = await worker.health_check()

        return {
            "router_status": "healthy",
            "workers": worker_health,
        }
