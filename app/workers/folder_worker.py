"""Folder Worker for RIP."""

from typing import Any

from app.core.logger import get_logger
from app.schemas.messages import WorkerRequest
from app.workers.base import BaseWorker

logger = get_logger(__name__)


class FolderWorker(BaseWorker):
    """Worker for folder/file operations."""

    def __init__(self):
        """Initialize folder worker."""
        super().__init__(worker_id="folder_worker", name="Folder Worker")

    async def validate(self, request: WorkerRequest) -> bool:
        """
        Validate folder worker request.

        Args:
            request: Worker request

        Returns:
            True if valid
        """
        valid_actions = ["list_files", "create_folder", "delete_file", "read_file"]

        if request.action not in valid_actions:
            return False

        return True

    async def process(self, request: WorkerRequest) -> dict[str, Any]:
        """
        Process folder request.

        Args:
            request: Worker request

        Returns:
            Processing result
        """
        action = request.action
        payload = request.payload

        logger.info(f"Folder Worker processing: {action}")

        # Return mock data for Phase 1
        if action == "list_files":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "path": payload.get("path", "/data"),
                    "files": [
                        {"name": "file1.txt", "size": "1KB", "type": "file"},
                        {"name": "file2.pdf", "size": "100KB", "type": "file"},
                        {"name": "subfolder", "type": "folder"},
                    ],
                    "total_files": 3,
                },
            }

        elif action == "create_folder":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "path": payload.get("path", "/data"),
                    "folder_name": payload.get("folder_name", "new_folder"),
                    "message": "資料夾已成功建立",
                },
            }

        elif action == "delete_file":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "file_name": payload.get("file_name", "file.txt"),
                    "message": "檔案已成功刪除",
                    "require_confirmation": True,
                },
            }

        elif action == "read_file":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "file_name": payload.get("file_name", "file.txt"),
                    "content": "這是檔案內容的模擬數據。\nPhase 1 演示文本。",
                    "size": "200B",
                },
            }

        return {
            "status": "error",
            "error": f"Unknown action: {action}",
        }
