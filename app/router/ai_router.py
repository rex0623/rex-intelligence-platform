"""AI Router for RIP - The Brain of the System."""

import uuid
from typing import Any

from app.core.logger import get_logger
from app.schemas.messages import WorkerRequest
from app.workers import ClaudeWorker, FolderWorker, GPTWorker, PDFWorker
from app.workflows.engine import WorkflowEngine
from app.approvals.manager import approval_manager

workflow_engine = WorkflowEngine()

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

        if worker_id == "folder_worker":
            folder_name = self._extract_folder_name(message)
            worker_request = WorkerRequest(
                worker_id=worker_id,
                action="analyze_folder",
                # empty folder_name means analyze the safe root itself
                payload={"folder_name": folder_name},
                user_id=user_id,
                request_id=str(uuid.uuid4()),
            )
            worker = self.workers[worker_id]
            worker_response = await worker.execute(worker_request)
            response_payload = worker_response.model_dump()
            return {
                "status": "success",
                "user_id": user_id,
                "intent": intent,
                "worker_id": worker_id,
                "worker_response": response_payload,
                "response": response_payload,
            }
        if worker_id == "pdf_worker":
            # If message explicitly about 電費單, create a pdf_bill workflow plan instead of returning PDF analysis
            if "電費單" in message or "電費" in message:
                plan = workflow_engine.create_workflow("pdf_bill", title="電費單處理流程")
                payload = plan.model_dump()
                # create an approval for this workflow plan
                approval = approval_manager.create_approval(payload)
                payload["approval_id"] = approval.approval_id
                return {
                    "status": "success",
                    "user_id": user_id,
                    "intent": intent,
                    "worker_id": worker_id,
                    "worker_response": payload,
                    "response": payload,
                }
            # otherwise fallback to analyzing PDFs directly
            worker_request = WorkerRequest(
                worker_id=worker_id,
                action="analyze_pdfs",
                payload={},
                user_id=user_id,
                request_id=str(uuid.uuid4()),
            )
            worker = self.workers[worker_id]
            worker_response = await worker.execute(worker_request)
            response_payload = worker_response.model_dump()
            return {
                "status": "success",
                "user_id": user_id,
                "intent": intent,
                "worker_id": worker_id,
                "worker_response": response_payload,
                "response": response_payload,
            }

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

    def _extract_folder_name(self, message: str) -> str:
        """
        Extract target folder name from the message.

        Args:
            message: User message

        Returns:
            Folder name
        """
        message_lower = message.lower()

        # explicit patterns: folder:xxx or 資料夾 xxx -> interpret as subfolder under safe root
        if "folder:" in message_lower:
            try:
                return message.split("folder:", 1)[1].strip()
            except Exception:
                return ""

        if "資料夾" in message:
            # look for token after 資料夾
            parts = message.split()
            for i, tok in enumerate(parts):
                if "資料夾" in tok and i + 1 < len(parts):
                    return parts[i + 1]

        # If user mentions Downloads without explicit folder indicator, treat as request to analyze safe_root itself
        if "downloads" in message_lower:
            return ""

        # Fallback: try to find a token that isn't a common verb
        tokens = message.split()
        for token in tokens:
            if token.lower() not in {"整理", "幫我", "請", "我", "的", "資料夾", "download", "downloads"}:
                return token

        return ""

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
