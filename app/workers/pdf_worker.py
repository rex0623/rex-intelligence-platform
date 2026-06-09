"""PDF Worker for RIP."""

from typing import Any

from app.core.logger import get_logger
from app.schemas.messages import WorkerRequest
from app.workers.base import BaseWorker

logger = get_logger(__name__)


class PDFWorker(BaseWorker):
    """Worker for PDF processing."""

    def __init__(self):
        """Initialize PDF worker."""
        super().__init__(worker_id="pdf_worker", name="PDF Worker")

    async def validate(self, request: WorkerRequest) -> bool:
        """
        Validate PDF worker request.

        Args:
            request: Worker request

        Returns:
            True if valid
        """
        if request.action not in ["extract_text", "extract_images", "extract_tables"]:
            return False

        return True

    async def process(self, request: WorkerRequest) -> dict[str, Any]:
        """
        Process PDF request.

        Args:
            request: Worker request

        Returns:
            Processing result
        """
        action = request.action
        payload = request.payload

        logger.info(f"PDF Worker processing: {action}")

        # Return mock data for Phase 1
        if action == "extract_text":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "text": "這是從 PDF 提取的模擬文本。\n"
                    "PDF 文件已成功處理。\n"
                    "此為 Phase 1 的演示數據。",
                    "pages": 5,
                    "file_name": payload.get("file_name", "document.pdf"),
                },
            }

        elif action == "extract_images":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "images": [
                        {"id": 1, "page": 1, "size": "100KB"},
                        {"id": 2, "page": 3, "size": "150KB"},
                    ],
                    "file_name": payload.get("file_name", "document.pdf"),
                },
            }

        elif action == "extract_tables":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "tables": [
                        {
                            "id": 1,
                            "page": 2,
                            "rows": 10,
                            "columns": 5,
                            "preview": "Table 1 data preview...",
                        }
                    ],
                    "file_name": payload.get("file_name", "document.pdf"),
                },
            }

        return {
            "status": "error",
            "error": f"Unknown action: {action}",
        }
