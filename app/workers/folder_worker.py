"""Folder Worker for RIP."""

import os
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.schemas.messages import WorkerRequest
from app.workers.base import BaseWorker

logger = get_logger(__name__)


class FolderWorker(BaseWorker):
    """Worker for folder/file operations."""

    def __init__(self):
        """Initialize folder worker."""
        super().__init__(worker_id="folder_worker", name="Folder Worker")
        self.safe_root = Path(settings.SAFE_FOLDER_ROOT).expanduser().resolve()

    async def validate(self, request: WorkerRequest) -> bool:
        """
        Validate folder worker request.

        Args:
            request: Worker request

        Returns:
            True if valid
        """
        valid_actions = [
            "list_files",
            "create_folder",
            "delete_file",
            "read_file",
            "analyze_folder",
        ]

        return request.action in valid_actions

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

        if action == "analyze_folder":
            return self._analyze_folder(payload)

        # Return mock data for other folder actions
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

    def _analyze_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        folder_name = payload.get("folder_name", "")

        # If no folder_name provided, analyze the safe root itself
        if not folder_name:
            target_path = self.safe_root
        else:
            requested_path = Path(folder_name)
            if requested_path.is_absolute():
                target_path = requested_path.resolve()
            else:
                target_path = (self.safe_root / requested_path).resolve()

        if not self._is_in_safe_root(target_path):
            return {
                "status": "error",
                "action": "analyze_folder",
                "error": "目錄不在安全根目錄內，已拒絕掃描。",
            }

        if not target_path.exists():
            return {
                "status": "error",
                "action": "analyze_folder",
                "error": f"資料夾不存在：{target_path}",
            }

        if not target_path.is_dir():
            return {
                "status": "error",
                "action": "analyze_folder",
                "error": f"指定路徑不是資料夾：{target_path}",
            }

        counts = self._count_extensions(target_path)
        suggestions = self._suggest_folders(counts)
        total_files = sum(counts.values())

        return {
            "status": "success",
            "action": "analyze_folder",
            "data": {
                "path": str(target_path),
                "safe_root": str(self.safe_root),
                "total_files": total_files,
                "extension_counts": counts,
                "suggested_folders": suggestions,
                "dry_run": True,
                "message": "已完成資料夾分析，這是 dry-run 模式，不會搬移或刪除檔案。",
            },
        }

    def _is_in_safe_root(self, target_path: Path) -> bool:
        try:
            return target_path.is_relative_to(self.safe_root)
        except Exception:
            return False

    def _count_extensions(self, target_path: Path) -> dict[str, int]:
        extension_counts: dict[str, int] = {}

        for item in target_path.rglob("*"):
            if item.is_file():
                ext = item.suffix.lower().lstrip(".") or "no_ext"
                extension_counts[ext] = extension_counts.get(ext, 0) + 1

        return extension_counts

    def _suggest_folders(self, counts: dict[str, int]) -> list[str]:
        suggestions: list[str] = []
        if not counts:
            return suggestions

        for ext in sorted(counts.keys()):
            if ext in {"pdf"}:
                suggestions.append("文檔")
            elif ext in {"xlsx", "xls", "csv"}:
                suggestions.append("報表")
            elif ext in {"png", "jpg", "jpeg", "gif"}:
                suggestions.append("圖片")
            elif ext in {"txt", "md"}:
                suggestions.append("文字檔")
            else:
                suggestions.append("其他")

        return sorted(set(suggestions))
