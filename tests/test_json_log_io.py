"""Phase 18C 測試：Shared JSON transaction log I/O helpers。

驗證重點：
- read_json_log 在不存在 / corrupted / wrong structure 時回 {"transactions": []}
- write_json_log 寫入後可 roundtrip；UTF-8 中文不被破壞
- write_json_log 自動建立 parent directory
- ensure_utc_aware 補 UTC 給 naive datetime；有 tzinfo 的原樣回傳
- RenameTransactionLog._read() 委派後行為不變
- MoveTransactionLog._write() 委派後行為不變
- 不產生 SQLite 或其他 DB 檔案
- 使用 tmp_path，不碰真實 runtime/
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.json_log_io import ensure_utc_aware, read_json_log, write_json_log


# ---------------------------------------------------------------------------
# read_json_log 測試
# ---------------------------------------------------------------------------


def test_read_json_log_nonexistent(tmp_path: Path):
    result = read_json_log(tmp_path / "nope.json")
    assert result == {"transactions": []}


def test_read_json_log_valid(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    payload = {"transactions": [{"transaction_id": "abc", "plan_id": "p1"}]}
    log_path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_json_log(log_path)

    assert result == payload
    assert result["transactions"][0]["transaction_id"] == "abc"


def test_read_json_log_invalid_json(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    log_path.write_text("{ NOT VALID JSON !!!", encoding="utf-8")

    result = read_json_log(log_path)

    assert result == {"transactions": []}


def test_read_json_log_wrong_structure_not_dict(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    log_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    result = read_json_log(log_path)

    assert result == {"transactions": []}


def test_read_json_log_wrong_structure_missing_key(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    log_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

    result = read_json_log(log_path)

    assert result == {"transactions": []}


def test_read_json_log_wrong_structure_transactions_not_list(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    log_path.write_text(json.dumps({"transactions": "not-a-list"}), encoding="utf-8")

    result = read_json_log(log_path)

    assert result == {"transactions": []}


def test_read_json_log_empty_transactions(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    log_path.write_text(json.dumps({"transactions": []}), encoding="utf-8")

    result = read_json_log(log_path)

    assert result == {"transactions": []}


def test_read_json_log_does_not_modify_file(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    original = "{ NOT VALID JSON !!!"
    log_path.write_text(original, encoding="utf-8")

    read_json_log(log_path)

    assert log_path.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# write_json_log 測試
# ---------------------------------------------------------------------------


def test_write_json_log_creates_file(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    data = {"transactions": []}

    write_json_log(log_path, data)

    assert log_path.exists()


def test_write_json_log_creates_parent_dirs(tmp_path: Path):
    log_path = tmp_path / "deep" / "nested" / "tx.json"

    write_json_log(log_path, {"transactions": []})

    assert log_path.exists()


def test_write_json_log_encoding(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    data = {"transactions": [{"plan_id": "台電電費單整理計畫"}]}

    write_json_log(log_path, data)

    raw = log_path.read_text(encoding="utf-8")
    assert "台電電費單整理計畫" in raw, "中文不應被 ascii escape"
    assert "\\u" not in raw, "ensure_ascii=False：不應有 unicode escape"


def test_write_json_log_uses_indent_2(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    data = {"transactions": [{"a": 1}]}

    write_json_log(log_path, data)

    raw = log_path.read_text(encoding="utf-8")
    assert "\n  " in raw, "indent=2 應有縮排"


def test_write_read_roundtrip(tmp_path: Path):
    log_path = tmp_path / "tx.json"
    original = {
        "transactions": [
            {"transaction_id": "tx-001", "plan_id": "plan-1", "actions": []},
            {"transaction_id": "tx-002", "plan_id": "plan-2", "actions": []},
        ]
    }

    write_json_log(log_path, original)
    result = read_json_log(log_path)

    assert result == original


def test_write_json_log_no_extra_files(tmp_path: Path):
    log_path = tmp_path / "tx.json"

    write_json_log(log_path, {"transactions": []})

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "tx.json"


# ---------------------------------------------------------------------------
# ensure_utc_aware 測試
# ---------------------------------------------------------------------------


def test_ensure_utc_aware_naive(tmp_path: Path):
    naive = datetime(2026, 1, 15, 10, 30, 0)
    assert naive.tzinfo is None

    result = ensure_utc_aware(naive)

    assert result.tzinfo is not None
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 15
    assert result.hour == 10
    assert result.minute == 30


def test_ensure_utc_aware_already_aware():
    aware = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)

    result = ensure_utc_aware(aware)

    assert result is aware or result == aware
    assert result.tzinfo is not None


def test_ensure_utc_aware_preserves_microseconds():
    naive = datetime(2026, 3, 1, 8, 0, 0, 123456)

    result = ensure_utc_aware(naive)

    assert result.microsecond == 123456


# ---------------------------------------------------------------------------
# RenameTransactionLog 委派整合測試
# ---------------------------------------------------------------------------


def test_rename_log_delegates_read(tmp_path: Path):
    """RenameTransactionLog._read() 委派後行為與原本相同。"""
    from app.filename.transaction_log import RenameTransactionLog

    log_path = tmp_path / "tx.json"
    log = RenameTransactionLog(log_path)

    # 不存在 → 空結構
    assert log._read() == {"transactions": []}

    # 損壞 JSON → 空結構
    log_path.write_text("NOT JSON", encoding="utf-8")
    assert log._read() == {"transactions": []}

    # 正常 JSON
    data = {"transactions": [{"transaction_id": "t1", "plan_id": "p1"}]}
    log_path.write_text(json.dumps(data), encoding="utf-8")
    assert log._read() == data


def test_move_log_delegates_write(tmp_path: Path):
    """MoveTransactionLog._write() 委派後行為與原本相同。"""
    from app.folder_intelligence.transaction_log import MoveTransactionLog

    log_path = tmp_path / "logs" / "move_tx.json"
    log = MoveTransactionLog(log_path)

    data = {"transactions": [{"transaction_id": "m1", "plan_id": "mp1"}]}
    log._write(data)

    assert log_path.exists()
    raw = json.loads(log_path.read_text(encoding="utf-8"))
    assert raw == data


def test_rename_log_save_and_load_via_helpers(tmp_path: Path):
    """RenameTransactionLog 的 save/load 端到端測試（委派後行為不變）。"""
    from app.filename.transaction_log import RenameTransactionLog
    from app.filename.schemas import RenameTransaction, RenameTransactionAction

    log_path = tmp_path / "tx.json"
    log = RenameTransactionLog(log_path)
    tx = RenameTransaction(
        plan_id="plan-e2e",
        actions=[
            RenameTransactionAction(
                original_path="/tmp/a.pdf",
                new_path="/tmp/b.pdf",
                status="success",
                rollback_from="/tmp/b.pdf",
                rollback_to="/tmp/a.pdf",
            )
        ],
    )

    log.save_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)

    assert loaded is not None
    assert loaded.plan_id == "plan-e2e"
    assert loaded.actions[0].status == "success"

    # JSON schema 不變：仍是 {"transactions": [...]} wrapper
    raw = json.loads(log_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "transactions" in raw
    assert isinstance(raw["transactions"], list)
