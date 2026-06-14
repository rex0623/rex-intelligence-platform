"""Phase 18E 測試：Transaction log Protocol definitions.

驗證重點：
- RenameTransactionLog 滿足 RenameTransactionLogProtocol（isinstance True）
- MoveTransactionLog 滿足 MoveTransactionLogProtocol（isinstance True）
- Protocol 不包含 prune_transactions（不強制要求任何 backend 實作 prune）
- Protocol module 不 import sqlite3 / sqlalchemy
- @runtime_checkable 使 isinstance 在 runtime 不 raise TypeError
- 使用 tmp_path，不碰真實 runtime/
- 不產生 SQLite / DB 檔案
"""

import ast
import importlib.util
from pathlib import Path

import pytest

from app.core.transaction_log_protocol import (
    MoveTransactionLogProtocol,
    RenameTransactionLogProtocol,
)
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence.transaction_log import MoveTransactionLog


# ---------------------------------------------------------------------------
# isinstance / structural subtyping tests
# ---------------------------------------------------------------------------


def test_rename_transaction_log_satisfies_protocol(tmp_path: Path):
    log = RenameTransactionLog(tmp_path / "rename.json")
    assert isinstance(log, RenameTransactionLogProtocol)


def test_move_transaction_log_satisfies_protocol(tmp_path: Path):
    log = MoveTransactionLog(tmp_path / "move.json")
    assert isinstance(log, MoveTransactionLogProtocol)


# ---------------------------------------------------------------------------
# Protocol scope: prune excluded
# ---------------------------------------------------------------------------


def test_rename_protocol_excludes_prune():
    assert "prune_transactions" not in RenameTransactionLogProtocol.__protocol_attrs__


def test_move_protocol_excludes_prune():
    assert "prune_transactions" not in MoveTransactionLogProtocol.__protocol_attrs__


# ---------------------------------------------------------------------------
# Callable method presence on concrete instances
# ---------------------------------------------------------------------------


def test_rename_protocol_methods_are_callable(tmp_path: Path):
    log = RenameTransactionLog(tmp_path / "rename.json")
    assert callable(log.save_transaction)
    assert callable(log.load_transaction)
    assert callable(log.list_transactions)
    assert callable(log.update_transaction)
    assert callable(log.mark_transaction_actions)


def test_move_protocol_methods_are_callable(tmp_path: Path):
    log = MoveTransactionLog(tmp_path / "move.json")
    assert callable(log.save_transaction)
    assert callable(log.load_transaction)
    assert callable(log.list_transactions)
    assert callable(log.update_transaction)
    assert callable(log.mark_transaction_actions)


# ---------------------------------------------------------------------------
# Protocol module must not import sqlite3 / sqlalchemy
# ---------------------------------------------------------------------------


def test_protocol_module_does_not_import_sqlite():
    spec = importlib.util.find_spec("app.core.transaction_log_protocol")
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "sqlite" not in alias.name.lower(), (
                    f"Unexpected sqlite import: {alias.name}"
                )
                assert "sqlalchemy" not in alias.name.lower(), (
                    f"Unexpected sqlalchemy import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "sqlite" not in module.lower(), (
                f"Unexpected sqlite import from: {module}"
            )
            assert "sqlalchemy" not in module.lower(), (
                f"Unexpected sqlalchemy import from: {module}"
            )


# ---------------------------------------------------------------------------
# @runtime_checkable: isinstance must not raise TypeError
# ---------------------------------------------------------------------------


def test_protocol_runtime_checkable():
    try:
        isinstance(object(), RenameTransactionLogProtocol)
        isinstance(object(), MoveTransactionLogProtocol)
    except TypeError as exc:
        pytest.fail(
            f"Protocol is not @runtime_checkable — isinstance raised TypeError: {exc}"
        )
