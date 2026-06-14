"""Configuration management for RIP."""

import os
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Application
    APP_NAME: str = "Rex Intelligence Platform"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Line
    LINE_CHANNEL_ID: str = ""
    LINE_CHANNEL_SECRET: str = ""
    LINE_ACCESS_TOKEN: str = ""

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/rip_dev"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # API Keys
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GITHUB_TOKEN: str = ""

    # AWS
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # Features
    ENABLE_RAG: bool = False
    ENABLE_MCP: bool = False
    ENABLE_AGENT: bool = False
    ENABLE_TASK_QUEUE: bool = False

    SAFE_FOLDER_ROOT: str = str(
        Path(__file__).resolve().parents[2] / "workspace" / "sandbox" / "inbox"
    )

    SAFE_PDF_ROOT: str = str(
        Path(__file__).resolve().parents[2] / "workspace" / "sandbox" / "pdf_inbox"
    )

    # Runtime artifacts (Phase 16B — consolidated; all gitignored)
    RUNTIME_DIR: str = str(Path(__file__).resolve().parents[2] / "runtime")

    # Persistence backend (Phase 19D — optional; default json)
    # "json"   → JSON flat-file backend (default, production-safe)
    # "sqlite" → Experimental SQLite backend; no migration yet; prune not supported
    TRANSACTION_LOG_BACKEND: Literal["json", "sqlite"] = "json"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()


# ---------------------------------------------------------------------------
# Phase 16B — Runtime path helpers（集中 runtime 路徑；動態讀取 settings，
# 測試以 monkeypatch.setattr(settings, "RUNTIME_DIR", ...) 即可覆寫）
# ---------------------------------------------------------------------------


def get_runtime_dir() -> Path:
    """Return the runtime artifacts directory (default: <repo>/runtime)."""
    return Path(settings.RUNTIME_DIR)


def get_approval_store_path() -> Path:
    """Default approval store path: runtime/approvals.json（gitignored）。"""
    return get_runtime_dir() / "approvals.json"


def get_rename_transaction_log_path() -> Path:
    """Default rename transaction log: runtime/rename_transactions.json。"""
    return get_runtime_dir() / "rename_transactions.json"


def get_move_transaction_log_path() -> Path:
    """Default move transaction log: runtime/move_transactions.json。"""
    return get_runtime_dir() / "move_transactions.json"


def get_sqlite_db_path() -> Path:
    """Default SQLite database path: runtime/rip.db（gitignored）。

    Returns a Path only — does NOT create the file or parent directories.
    The file is created on first use by initialize_sqlite_schema().
    Only called when TRANSACTION_LOG_BACKEND == "sqlite".
    """
    return get_runtime_dir() / "rip.db"


def get_safe_pdf_root() -> Path:
    """Return SAFE_PDF_ROOT as a Path (PDF planning / execution root)."""
    return Path(settings.SAFE_PDF_ROOT)


def resolve_under_safe_root(path: str | Path, root: Path | None = None) -> Path:
    """Resolve *path* for executor-level filesystem access (Phase 16B).

    - Absolute path → returned unchanged（既有語意：絕對路徑不受 safe root
      限制，呼叫端一律以絕對 tmp_path 操作）。
    - Relative path → anchored under *root*（預設 get_safe_pdf_root()），
      以字串正規化（os.path.normpath）處理，不觸碰 filesystem、
      不解析 symlink、檔案不存在也不會 throw。
    - Relative path 經正規化後逃出 root（path traversal，如 "../../etc"）
      → raise ValueError("path_escapes_safe_root")；executor 呼叫端
      以 failed result fail-safe 處理，不操作任何檔案。
    """
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate

    if root is None:
        root = get_safe_pdf_root()
    root_norm = Path(os.path.normpath(str(Path(root).absolute())))
    resolved = Path(os.path.normpath(str(root_norm / candidate)))

    if resolved != root_norm and root_norm not in resolved.parents:
        raise ValueError(f"path_escapes_safe_root: {path}")
    return resolved
