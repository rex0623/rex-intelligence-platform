"""Phase 14C 測試：Persistent Transaction Log & Rollback Audit Trail。

所有涉及真實檔案系統操作的測試，一律使用 pytest tmp_path，
不修改任何真實專案檔案。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.filename.executor import (
    execute_rename_plan,
    rollback_transaction_by_id,
)
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenameTransaction,
    RenameTransactionAction,
    RenamePlan,
    ValidationReport,
)
from app.filename.transaction_log import RenameTransactionLog


# ---------------------------------------------------------------------------
# 測試輔助函式
# ---------------------------------------------------------------------------


def _make_transaction(plan_id: str = "plan-001", n_actions: int = 1) -> RenameTransaction:
    actions = [
        RenameTransactionAction(
            original_path=f"/tmp/orig_{i}.pdf",
            new_path=f"/tmp/renamed_{i}.pdf",
            status="pending",
            rollback_from=f"/tmp/renamed_{i}.pdf",
            rollback_to=f"/tmp/orig_{i}.pdf",
        )
        for i in range(n_actions)
    ]
    return RenameTransaction(plan_id=plan_id, actions=actions)


def _make_plan(
    candidates: list[RenameCandidate],
    risk_levels: list[str],
    status: str = "approved",
) -> RenamePlan:
    plan = RenamePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)
    cv_list = [
        CandidateValidation(
            original_filename=c.original_filename,
            proposed_filename=c.proposed_filename,
            risk_level=rl,
        )
        for c, rl in zip(candidates, risk_levels)
    ]
    plan.validation_report = ValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=sum(1 for r in risk_levels if r == "blocked"),
        candidates=cv_list,
    )
    return plan


def _write_file(path: Path, content: str = "dummy") -> Path:
    path.write_text(content)
    return path


def _low_candidate(tmp_path: Path, orig: str, proposed: str) -> RenameCandidate:
    return RenameCandidate(
        original_filename=str(tmp_path / orig),
        proposed_filename=str(tmp_path / proposed),
        confidence=1.0,
        document_type="taipower_bill",
    )


# ---------------------------------------------------------------------------
# 測試 1：save_transaction 建立 log 檔案
# ---------------------------------------------------------------------------


def test_save_transaction_creates_log_file(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx = _make_transaction("plan-1")

    assert not (tmp_path / "tx.json").exists()
    log.save_transaction(tx)
    assert (tmp_path / "tx.json").exists()


# ---------------------------------------------------------------------------
# 測試 2：list_transactions 在 log 不存在時回傳空 list
# ---------------------------------------------------------------------------


def test_list_transactions_returns_empty_when_missing(tmp_path):
    log = RenameTransactionLog(tmp_path / "nonexistent.json")
    result = log.list_transactions()
    assert result == []


# ---------------------------------------------------------------------------
# 測試 3：save 後 load_transaction 可取回同一筆 transaction
# ---------------------------------------------------------------------------


def test_save_then_load_transaction(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx = _make_transaction("plan-abc", n_actions=2)

    log.save_transaction(tx)
    loaded = log.load_transaction(tx.transaction_id)

    assert loaded is not None
    assert loaded.transaction_id == tx.transaction_id
    assert loaded.plan_id == tx.plan_id
    assert len(loaded.actions) == 2
    assert loaded.actions[0].original_path == tx.actions[0].original_path


# ---------------------------------------------------------------------------
# 測試 4：update_transaction 取代既有 transaction
# ---------------------------------------------------------------------------


def test_update_transaction_replaces_existing(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx = _make_transaction("plan-x")
    log.save_transaction(tx)

    # 修改 action status 後更新
    updated_tx = RenameTransaction(
        transaction_id=tx.transaction_id,
        plan_id=tx.plan_id,
        created_at=tx.created_at,
        actions=[
            RenameTransactionAction(
                original_path=tx.actions[0].original_path,
                new_path=tx.actions[0].new_path,
                status="success",
                rollback_from=tx.actions[0].rollback_from,
                rollback_to=tx.actions[0].rollback_to,
            )
        ],
    )
    log.update_transaction(updated_tx)

    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert loaded.actions[0].status == "success"

    # 確認 log 中只有一筆 transaction
    all_txs = log.list_transactions()
    assert len(all_txs) == 1


# ---------------------------------------------------------------------------
# 測試 5：save_transaction 不覆蓋其他不相關的 transaction
# ---------------------------------------------------------------------------


def test_save_transaction_does_not_overwrite_unrelated(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx1 = _make_transaction("plan-1")
    tx2 = _make_transaction("plan-2")

    log.save_transaction(tx1)
    log.save_transaction(tx2)

    all_txs = log.list_transactions()
    assert len(all_txs) == 2

    ids = {t.transaction_id for t in all_txs}
    assert tx1.transaction_id in ids
    assert tx2.transaction_id in ids


# ---------------------------------------------------------------------------
# 測試 6：datetime 序列化與反序列化正確
# ---------------------------------------------------------------------------


def test_datetime_serialization_and_deserialization(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    tx = RenameTransaction(plan_id="plan-dt", created_at=now)
    log.save_transaction(tx)

    # 驗證 JSON 內容是 ISO 字串
    raw = json.loads((tmp_path / "tx.json").read_text())
    stored_dt = raw["transactions"][0]["created_at"]
    assert isinstance(stored_dt, str), "datetime 必須以字串形式存入 JSON"
    assert "2026-06-10" in stored_dt

    # 驗證反序列化後恢復為 datetime 物件
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded is not None
    assert isinstance(loaded.created_at, datetime)
    assert loaded.created_at.year == 2026
    assert loaded.created_at.month == 6


# ---------------------------------------------------------------------------
# 測試 7：mark_transaction_actions 透過 original_path 更新 status
# ---------------------------------------------------------------------------


def test_mark_transaction_actions_by_original_path(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx = _make_transaction("plan-m", n_actions=1)
    log.save_transaction(tx)

    orig_path = tx.actions[0].original_path
    updated = log.mark_transaction_actions(
        tx.transaction_id, {orig_path: "success"}
    )

    assert updated is not None
    assert updated.actions[0].status == "success"

    # 確認 log 同步更新
    loaded = log.load_transaction(tx.transaction_id)
    assert loaded.actions[0].status == "success"


# ---------------------------------------------------------------------------
# 測試 8：mark_transaction_actions 透過 new_path 更新 status
# ---------------------------------------------------------------------------


def test_mark_transaction_actions_by_new_path(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx = _make_transaction("plan-n", n_actions=1)
    log.save_transaction(tx)

    new_path = tx.actions[0].new_path
    updated = log.mark_transaction_actions(
        tx.transaction_id, {new_path: "failed"}
    )

    assert updated is not None
    assert updated.actions[0].status == "failed"


# ---------------------------------------------------------------------------
# 測試 9：mark_transaction_actions 找不到 transaction 時回傳 None
# ---------------------------------------------------------------------------


def test_mark_transaction_actions_returns_none_for_unknown_id(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    result = log.mark_transaction_actions("nonexistent-id", {"some/path": "success"})
    assert result is None


# ---------------------------------------------------------------------------
# 測試 10：execute_rename_plan with transaction_log 會持久化 transaction
# ---------------------------------------------------------------------------


def test_execute_with_log_persists_transaction(tmp_path):
    c = _low_candidate(tmp_path, "bill.pdf", "renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log_path = tmp_path / "tx_log.json"
    log = RenameTransactionLog(log_path)

    execute_rename_plan(plan, transaction_log=log)

    assert log_path.exists(), "log 檔案應在執行後被建立"
    txs = log.list_transactions()
    assert len(txs) == 1
    assert txs[0].plan_id == plan.plan_id


# ---------------------------------------------------------------------------
# 測試 11：execute_rename_plan with transaction_log 更新成功 action 的 status
# ---------------------------------------------------------------------------


def test_execute_with_log_updates_successful_action_status(tmp_path):
    c = _low_candidate(tmp_path, "source.pdf", "target.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log = RenameTransactionLog(tmp_path / "tx_log.json")
    result = execute_rename_plan(plan, transaction_log=log)

    assert result.success_count == 1

    txs = log.list_transactions()
    assert len(txs) == 1
    # action status 應從 "pending" 更新為 "success"
    assert txs[0].actions[0].status == "success"
    assert txs[0].actions[0].original_path == c.original_filename


# ---------------------------------------------------------------------------
# 測試 12：execute_rename_plan 不提供 transaction_log 仍正常運作
# ---------------------------------------------------------------------------


def test_execute_without_log_still_works(tmp_path):
    c = _low_candidate(tmp_path, "a.pdf", "b.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    result = execute_rename_plan(plan)  # no transaction_log

    assert result.success_count == 1
    assert Path(c.proposed_filename).exists()


# ---------------------------------------------------------------------------
# 測試 13：rollback_transaction_by_id 找不到時回傳 transaction_not_found
# ---------------------------------------------------------------------------


def test_rollback_by_id_returns_not_found_for_missing(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")

    result = rollback_transaction_by_id("ghost-id", log)

    assert result.executed is False
    assert result.failed_count == 1
    assert result.results[0].reason == "transaction_not_found"


# ---------------------------------------------------------------------------
# 測試 14：rollback_transaction_by_id 從持久化 transaction 正確回滾
# ---------------------------------------------------------------------------


def test_rollback_by_id_rolls_back_from_persisted_transaction(tmp_path):
    c = _low_candidate(tmp_path, "orig.pdf", "renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log = RenameTransactionLog(tmp_path / "tx.json")
    exec_result = execute_rename_plan(plan, transaction_log=log)

    assert exec_result.success_count == 1
    assert Path(c.proposed_filename).exists()
    assert not Path(c.original_filename).exists()

    # 取得 transaction_id
    txs = log.list_transactions()
    tx_id = txs[0].transaction_id

    rb_result = rollback_transaction_by_id(tx_id, log)

    assert rb_result.executed is True
    assert rb_result.success_count == 1
    assert Path(c.original_filename).exists(), "rollback 後原始檔應恢復"
    assert not Path(c.proposed_filename).exists(), "rollback 後更名後檔案應消失"


# ---------------------------------------------------------------------------
# 測試 15：rollback_transaction_by_id 更新 log 中 action 狀態為 rolled_back
# ---------------------------------------------------------------------------


def test_rollback_by_id_updates_log_action_to_rolled_back(tmp_path):
    c = _low_candidate(tmp_path, "file.pdf", "file_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log = RenameTransactionLog(tmp_path / "tx.json")
    execute_rename_plan(plan, transaction_log=log)

    txs = log.list_transactions()
    tx_id = txs[0].transaction_id

    # 確認執行後 action 狀態為 success
    assert txs[0].actions[0].status == "success"

    rollback_transaction_by_id(tx_id, log)

    # 確認 rollback 後 action 狀態更新為 rolled_back
    updated_tx = log.load_transaction(tx_id)
    assert updated_tx is not None
    assert updated_tx.actions[0].status == "rolled_back"


# ---------------------------------------------------------------------------
# 測試 16：rollback 失敗時不破壞 transaction log
# ---------------------------------------------------------------------------


def test_failed_rollback_does_not_corrupt_transaction_log(tmp_path):
    c = _low_candidate(tmp_path, "doc.pdf", "doc_renamed.pdf")
    _write_file(Path(c.original_filename))
    plan = _make_plan([c], ["low"])

    log = RenameTransactionLog(tmp_path / "tx.json")
    execute_rename_plan(plan, transaction_log=log)

    # 模擬「renamed 檔案消失」讓 rollback 失敗
    Path(c.proposed_filename).unlink()

    txs = log.list_transactions()
    tx_id = txs[0].transaction_id

    rb_result = rollback_transaction_by_id(tx_id, log)

    # rollback 失敗
    assert rb_result.executed is True
    assert rb_result.failed_count == 1

    # log 不應損壞：action 仍維持 "success"（rollback 失敗，檔案還沒回來）
    loaded = log.load_transaction(tx_id)
    assert loaded is not None
    assert len(loaded.actions) == 1
    assert loaded.actions[0].status == "success"  # rollback 失敗，不改狀態

    # 驗證 log 整體結構未損壞
    all_txs = log.list_transactions()
    assert len(all_txs) == 1


# ---------------------------------------------------------------------------
# 測試 17：損壞的 JSON 被安全處理，不拋出例外
# ---------------------------------------------------------------------------


def test_corrupted_json_handled_safely(tmp_path):
    log_file = tmp_path / "tx.json"
    log_file.write_text("{ this is not valid json !!!}", encoding="utf-8")
    log = RenameTransactionLog(log_file)

    # list_transactions 應回傳空 list，不應拋出例外
    result = log.list_transactions()
    assert result == []

    # load_transaction 應回傳 None，不應拋出例外
    loaded = log.load_transaction("some-id")
    assert loaded is None


# ---------------------------------------------------------------------------
# 額外測試 A：子目錄不存在時自動建立
# ---------------------------------------------------------------------------


def test_save_transaction_creates_parent_directories(tmp_path):
    deep_path = tmp_path / "a" / "b" / "c" / "tx.json"
    log = RenameTransactionLog(deep_path)
    tx = _make_transaction()

    log.save_transaction(tx)

    assert deep_path.exists()


# ---------------------------------------------------------------------------
# 額外測試 B：同一 transaction 多次 save 只保留一筆（upsert 語義）
# ---------------------------------------------------------------------------


def test_save_transaction_upserts_by_id(tmp_path):
    log = RenameTransactionLog(tmp_path / "tx.json")
    tx = _make_transaction("plan-upsert")
    log.save_transaction(tx)
    log.save_transaction(tx)  # 相同 id，再 save 一次

    all_txs = log.list_transactions()
    assert len(all_txs) == 1, "同一 transaction_id 不應產生重複紀錄"


# ---------------------------------------------------------------------------
# 額外測試 C：execute failed action 也更新 log status
# ---------------------------------------------------------------------------


def test_execute_with_log_updates_failed_action_status(tmp_path):
    """原始檔不存在 → failed → log 中 action 應更新為 failed。"""
    c = _low_candidate(tmp_path, "missing.pdf", "missing_renamed.pdf")
    # 刻意不建立原始檔
    plan = _make_plan([c], ["low"])

    log = RenameTransactionLog(tmp_path / "tx.json")
    result = execute_rename_plan(plan, transaction_log=log)

    assert result.failed_count == 1

    txs = log.list_transactions()
    assert len(txs) == 1
    assert txs[0].actions[0].status == "failed"
