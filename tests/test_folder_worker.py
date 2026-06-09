"""Tests for FolderWorker safe analysis mode."""

import asyncio
from pathlib import Path

from app.core.config import settings
from app.schemas.messages import WorkerRequest
from app.workers.folder_worker import FolderWorker


def test_folder_worker_empty_folder(tmp_path, monkeypatch):
    safe_root = tmp_path / "inbox"
    downloads = safe_root / "Downloads"
    downloads.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_FOLDER_ROOT", str(safe_root))

    worker = FolderWorker()
    request = WorkerRequest(
        worker_id="folder_worker",
        action="analyze_folder",
        payload={"folder_name": "Downloads"},
        user_id="test_user",
        request_id="1",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "success"
    assert data["data"]["data"]["total_files"] == 0
    assert data["data"]["data"]["extension_counts"] == {}
    assert data["data"]["data"]["suggested_folders"] == []
    assert data["data"]["data"]["dry_run"] is True


def test_folder_worker_file_types(tmp_path, monkeypatch):
    safe_root = tmp_path / "inbox"
    downloads = safe_root / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "document.pdf").write_text("pdf")
    (downloads / "report.xlsx").write_text("xlsx")
    (downloads / "image.png").write_text("png")
    (downloads / "notes.txt").write_text("txt")

    monkeypatch.setattr(settings, "SAFE_FOLDER_ROOT", str(safe_root))

    worker = FolderWorker()
    request = WorkerRequest(
        worker_id="folder_worker",
        action="analyze_folder",
        payload={"folder_name": "Downloads"},
        user_id="test_user",
        request_id="2",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "success"
    assert data["data"]["data"]["total_files"] == 4
    assert data["data"]["data"]["extension_counts"] == {"pdf": 1, "xlsx": 1, "png": 1, "txt": 1}
    assert set(data["data"]["data"]["suggested_folders"]) == {"文檔", "報表", "圖片", "文字檔"}
    assert data["data"]["data"]["dry_run"] is True


def test_folder_worker_nonexistent_folder(tmp_path, monkeypatch):
    safe_root = tmp_path / "inbox"
    safe_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_FOLDER_ROOT", str(safe_root))

    worker = FolderWorker()
    request = WorkerRequest(
        worker_id="folder_worker",
        action="analyze_folder",
        payload={"folder_name": "Downloads"},
        user_id="test_user",
        request_id="3",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "error"
    assert "資料夾不存在" in data["data"]["error"]


def test_folder_worker_rejects_non_safe_directory(tmp_path, monkeypatch):
    safe_root = tmp_path / "inbox"
    safe_root.mkdir(parents=True)
    forbidden_folder = tmp_path / "forbidden"
    forbidden_folder.mkdir(parents=True)

    monkeypatch.setattr(settings, "SAFE_FOLDER_ROOT", str(safe_root))

    worker = FolderWorker()
    request = WorkerRequest(
        worker_id="folder_worker",
        action="analyze_folder",
        payload={"folder_name": str(forbidden_folder)},
        user_id="test_user",
        request_id="4",
    )
    response = asyncio.run(worker.execute(request))
    data = response.model_dump()

    assert data["success"] is True
    assert data["data"]["status"] == "error"
    assert "拒絕掃描" in data["data"]["error"]
