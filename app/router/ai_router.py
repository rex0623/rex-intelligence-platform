"""AI Router for RIP - The Brain of the System."""

from typing import Any

from app.core.logger import get_logger
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
        message: str,
        user_id: str = "unknown",
        metadata: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        Route message to appropriate worker.

        Args:
            message: User message
            user_id: User ID
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

        intent = self._detect_intent(message)
        logger.info(
            "Intent detected",
            extra={"user_id": user_id, "intent": intent},
        )

        worker_id = self._select_worker(intent)
        logger.info(
            "Worker selected",
            extra={"user_id": user_id, "worker_id": worker_id},
        )

        worker_response = self._generate_fake_response(worker_id)

        return {
            "status": "success",
            "user_id": user_id,
            "intent": intent,
            "worker_id": worker_id,
            "worker_response": worker_response,
            "response": {"message": worker_response},
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
        if any(word in message_lower for word in ["電費單", "pdf", "PDF"]):
            return "pdf_processing"

        if any(word in message_lower for word in ["需求", "規格", "prd"]):
            return "requirements_analysis"

        if any(word in message_lower for word in ["整理", "downloads", "folder"]):
            return "file_management"

        if any(word in message_lower for word in ["寫程式", "code", "api"]):
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
            "requirements_analysis": "gpt_worker",
        }

        return intent_map.get(intent, "default")

    def _generate_fake_response(self, worker_id: str) -> str:
        """
        Generate fake response for the selected worker.

        Args:
            worker_id: Selected worker ID

        Returns:
            Text response from worker
        """
        if worker_id == "pdf_worker":
            return "我判斷這是 PDF 任務"

        if worker_id == "folder_worker":
            return "我判斷這是資料夾整理任務"

        if worker_id == "claude_worker":
            return "我判斷這是程式開發任務"

        if worker_id == "gpt_worker":
            return "我判斷這是需求分析任務"

        return "我還不確定你的需求，可以再說清楚一點嗎？"

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
