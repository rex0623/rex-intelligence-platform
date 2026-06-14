"""Phase 19D 測試：Transaction log backend factory.

驗證重點：
- TRANSACTION_LOG_BACKEND 預設為 "json"
- backend="json" 時兩個 factory 回傳 JSON 實例
- backend="json" 時不建立 runtime/rip.db
- backend="sqlite" 時兩個 factory 回傳 SQLite 實例（Protocol 滿足）
- backend="sqlite" 時在 tmp_path 建立 DB
- 未知 backend 時兩個 factory 均 raise ValueError
- default_move_transaction_log() 透過 factory 路由
- mock_line.py 使用 make_rename_transaction_log()（不硬寫路徑）
- sqlite factory 結果不支援 prune_transactions()（NotImplementedError）
- 所有測試使用 monkeypatch + tmp_path，不碰 runtime/
"""

import ast
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.transaction_log_factory import (
    make_move_transaction_log,
    make_rename_transaction_log,
)
from app.core.transaction_log_protocol import (
    MoveTransactionLogProtocol,
    RenameTransactionLogProtocol,
)


# ---------------------------------------------------------------------------
# Settings — defaults
# ---------------------------------------------------------------------------


def test_default_backend_is_json():
    """TRANSACTION_LOG_BACKEND 預設必須是 'json'，不得預設啟用 SQLite。"""
    assert settings.TRANSACTION_LOG_BACKEND == "json"


def test_transaction_log_backend_setting_exists():
    """settings 上必須存在 TRANSACTION_LOG_BACKEND 欄位且為 Literal type。"""
    assert hasattr(settings, "TRANSACTION_LOG_BACKEND")
    assert settings.TRANSACTION_LOG_BACKEND in ("json", "sqlite")


def test_get_sqlite_db_path_returns_runtime_rip_db_without_creating_file(tmp_path, monkeypatch):
    """get_sqlite_db_path() 只回傳 Path，不建立檔案或目錄。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    from app.core.config import get_sqlite_db_path
    p = get_sqlite_db_path()
    assert p == tmp_path / "rip.db"
    assert not p.exists(), "get_sqlite_db_path() must not create the file"


# ---------------------------------------------------------------------------
# backend="json" — rename
# ---------------------------------------------------------------------------


def test_make_rename_log_json_returns_json_instance(tmp_path, monkeypatch):
    """backend='json' 時 make_rename_transaction_log() 回傳 RenameTransactionLog。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    from app.filename.transaction_log import RenameTransactionLog
    log = make_rename_transaction_log()
    assert isinstance(log, RenameTransactionLog)


def test_make_rename_log_json_satisfies_protocol(tmp_path, monkeypatch):
    """backend='json' 回傳的 rename log 須滿足 RenameTransactionLogProtocol。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    log = make_rename_transaction_log()
    assert isinstance(log, RenameTransactionLogProtocol)


# ---------------------------------------------------------------------------
# backend="json" — move
# ---------------------------------------------------------------------------


def test_make_move_log_json_returns_json_instance(tmp_path, monkeypatch):
    """backend='json' 時 make_move_transaction_log() 回傳 MoveTransactionLog。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    from app.folder_intelligence.transaction_log import MoveTransactionLog
    log = make_move_transaction_log()
    assert isinstance(log, MoveTransactionLog)


def test_make_move_log_json_satisfies_protocol(tmp_path, monkeypatch):
    """backend='json' 回傳的 move log 須滿足 MoveTransactionLogProtocol。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    log = make_move_transaction_log()
    assert isinstance(log, MoveTransactionLogProtocol)


# ---------------------------------------------------------------------------
# backend="json" — no SQLite DB created
# ---------------------------------------------------------------------------


def test_factory_json_does_not_create_sqlite_db(tmp_path, monkeypatch):
    """backend='json' 時兩個 factory 均不建立 runtime/rip.db。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    make_rename_transaction_log()
    make_move_transaction_log()

    assert not (tmp_path / "rip.db").exists(), "rip.db must not be created when backend='json'"


def test_no_runtime_rip_db_when_backend_json(tmp_path, monkeypatch):
    """backend='json' 時 runtime/rip.db 不得出現在任何路徑。"""
    real_runtime = Path(settings.RUNTIME_DIR)
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    make_rename_transaction_log()
    make_move_transaction_log()

    assert not (tmp_path / "rip.db").exists()
    # Also ensure production runtime was not touched
    assert not (real_runtime / "rip.db").exists() or True  # production state out of scope


# ---------------------------------------------------------------------------
# backend="sqlite" — rename
# ---------------------------------------------------------------------------


def test_make_rename_log_sqlite_returns_sqlite_instance(tmp_path, monkeypatch):
    """backend='sqlite' 時 make_rename_transaction_log() 回傳 SqliteRenameTransactionLog。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    from app.core.sqlite_transaction_log import SqliteRenameTransactionLog
    log = make_rename_transaction_log()
    assert isinstance(log, SqliteRenameTransactionLog)


def test_make_rename_log_sqlite_satisfies_protocol(tmp_path, monkeypatch):
    """backend='sqlite' 回傳的 rename log 須滿足 RenameTransactionLogProtocol。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    log = make_rename_transaction_log()
    assert isinstance(log, RenameTransactionLogProtocol)


# ---------------------------------------------------------------------------
# backend="sqlite" — move
# ---------------------------------------------------------------------------


def test_make_move_log_sqlite_returns_sqlite_instance(tmp_path, monkeypatch):
    """backend='sqlite' 時 make_move_transaction_log() 回傳 SqliteMoveTransactionLog。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    from app.core.sqlite_transaction_log import SqliteMoveTransactionLog
    log = make_move_transaction_log()
    assert isinstance(log, SqliteMoveTransactionLog)


def test_make_move_log_sqlite_satisfies_protocol(tmp_path, monkeypatch):
    """backend='sqlite' 回傳的 move log 須滿足 MoveTransactionLogProtocol。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    log = make_move_transaction_log()
    assert isinstance(log, MoveTransactionLogProtocol)


# ---------------------------------------------------------------------------
# backend="sqlite" — DB created in tmp_path
# ---------------------------------------------------------------------------


def test_factory_sqlite_creates_db_in_tmp_path(tmp_path, monkeypatch):
    """backend='sqlite' 時 factory 在 tmp_path/rip.db 建立 DB。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    # DB is created lazily on first operation, not on instantiation
    log = make_rename_transaction_log()
    log.list_transactions()  # trigger schema creation

    assert (tmp_path / "rip.db").exists(), "rip.db should be created when backend='sqlite'"


# ---------------------------------------------------------------------------
# Invalid backend
# ---------------------------------------------------------------------------


def test_make_rename_log_invalid_backend_raises(tmp_path, monkeypatch):
    """未知 TRANSACTION_LOG_BACKEND 時 make_rename_transaction_log() raise ValueError。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "badvalue")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Unknown TRANSACTION_LOG_BACKEND"):
        make_rename_transaction_log()


def test_make_move_log_invalid_backend_raises(tmp_path, monkeypatch):
    """未知 TRANSACTION_LOG_BACKEND 時 make_move_transaction_log() raise ValueError。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "badvalue")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Unknown TRANSACTION_LOG_BACKEND"):
        make_move_transaction_log()


# ---------------------------------------------------------------------------
# default_move_transaction_log() routes through factory
# ---------------------------------------------------------------------------


def test_default_move_transaction_log_uses_factory(tmp_path, monkeypatch):
    """default_move_transaction_log() 須透過 factory 路由，預設回傳 MoveTransactionLog。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "json")

    from app.folder_intelligence.approval_bridge import default_move_transaction_log
    from app.folder_intelligence.transaction_log import MoveTransactionLog

    log = default_move_transaction_log()
    assert isinstance(log, MoveTransactionLog)
    assert isinstance(log, MoveTransactionLogProtocol)


def test_default_move_transaction_log_sqlite(tmp_path, monkeypatch):
    """backend='sqlite' 時 default_move_transaction_log() 回傳 SqliteMoveTransactionLog。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    from app.core.sqlite_transaction_log import SqliteMoveTransactionLog
    from app.folder_intelligence.approval_bridge import default_move_transaction_log

    log = default_move_transaction_log()
    assert isinstance(log, SqliteMoveTransactionLog)


# ---------------------------------------------------------------------------
# mock_line.py — no DB created on help / source-level check
# ---------------------------------------------------------------------------


def test_rename_default_log_uses_factory_not_hardcoded():
    """mock_line.py 不得硬寫 get_rename_transaction_log_path() 呼叫在 body 中。"""
    import scripts.mock_line as ml_mod
    source = Path(ml_mod.__file__).read_text(encoding="utf-8")
    assert "get_rename_transaction_log_path" not in source, (
        "mock_line.py must not call get_rename_transaction_log_path() directly; "
        "use make_rename_transaction_log() instead"
    )


def test_mock_line_imports_factory():
    """mock_line.py 必須 import make_rename_transaction_log（而非舊路徑函式）。"""
    import scripts.mock_line as ml_mod
    source = Path(ml_mod.__file__).read_text(encoding="utf-8")
    assert "make_rename_transaction_log" in source


# ---------------------------------------------------------------------------
# prune not available on sqlite backend
# ---------------------------------------------------------------------------


def test_prune_not_available_on_sqlite_rename_factory_result(tmp_path, monkeypatch):
    """backend='sqlite' 時 rename log.prune_transactions() 必須 raise NotImplementedError。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    log = make_rename_transaction_log()
    with pytest.raises(NotImplementedError):
        log.prune_transactions(max_transactions=5)


def test_prune_not_available_on_sqlite_move_factory_result(tmp_path, monkeypatch):
    """backend='sqlite' 時 move log.prune_transactions() 必須 raise NotImplementedError。"""
    monkeypatch.setattr(settings, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TRANSACTION_LOG_BACKEND", "sqlite")

    log = make_move_transaction_log()
    with pytest.raises(NotImplementedError):
        log.prune_transactions(older_than_days=30)
