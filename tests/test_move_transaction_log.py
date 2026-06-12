"""Phase 15E 測試：Move Transaction Log / Rollback Foundation。

- MoveTransactionLog 以 JSON 持久化 MoveTransaction（無資料庫依賴）
- execute_move_plan(plan, transaction_log=None)：未提供 log 時行為與 15D 相同
- rollback_move_transaction() 只回滾 status == "success" 的 action
- rollback_move_transaction_by_id() 從 log 載入、回滾並標記 rolled_back
- 所有真實 move / rollback 測試一律使用 pytest tmp_path
- Mock LINE 沒有任何指令會觸發真實搬移或 rollback
"""

import ast
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.folder_intelligence import (
    MoveTransaction,
    MoveTransactionAction,
    MoveTransactionLog,
    build_move_transaction,
    execute_move_plan,
    rollback_move_transaction,
    rollback_move_transaction_by_id,
)
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveValidationReport,
)


# ---------------------------------------------------------------------------
# 測試輔助（與 test_safe_move_executor.py 相同風格）
# ---------------------------------------------------------------------------


def _candidate(name: str, original_path: str, proposed_path: str) -> MoveCandidate:
    return MoveCandidate(
        original_path=original_path,
        original_filename=name,
        proposed_folder=str(Path(proposed_path).parent) + "/",
        proposed_path=proposed_path,
        document_type="taipower_bill",
        confidence=1.0,
    )


def _tmp_candidate(
    tmp_path: Path,
    name: str = "bill.pdf",
    target_subdir: str = "電費單/24581234/2026-05",
    create_source: bool = True,
) -> MoveCandidate:
    src = tmp_path / "inbox" / name
    if create_source:
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("content-" + name)
    target = tmp_path / target_subdir / name
    return _candidate(name, str(src), str(target))


def _make_plan(
    candidates: list[MoveCandidate],
    risk_levels: list[str],
    status: str = "approved",
) -> MovePlan:
    plan = MovePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)
    plan.validation_report = MoveValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=0,  # plan-level gate 不在本檔測試範圍
        candidates=[
            MoveCandidateValidation(
                original_filename=c.original_filename,
                proposed_folder=c.proposed_folder,
                proposed_path=c.proposed_path,
                risk_level=rl,
            )
            for c, rl in zip(candidates, risk_levels)
        ],
    )
    return plan


def _tx(tmp_path: Path, status: str = "success") -> MoveTransaction:
    """建立單一 action 的 transaction（不碰 filesystem）。"""
    original = str(tmp_path / "inbox" / "bill.pdf")
    new = str(tmp_path / "電費單" / "bill.pdf")
    return MoveTransaction(
        plan_id="plan-1",
        actions=[MoveTransactionAction(
            original_path=original,
            new_path=new,
            status=status,
            rollback_from=new,
            rollback_to=original,
        )],
    )


# ---------------------------------------------------------------------------
# 測試 1–6：MoveTransactionLog 基本持久化
# ---------------------------------------------------------------------------


def test_save_transaction_creates_log_file(tmp_path):
    log_path = tmp_path / "logs" / "move_transactions.json"
    log = MoveTransactionLog(log_path)

    log.save_transaction(_tx(tmp_path))

    assert log_path.exists(), "save_transaction 應自動建立 parent dir 與 JSON 檔"
    data = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(data["transactions"]) == 1


def test_list_transactions_returns_empty_when_missing(tmp_path):
    log = MoveTransactionLog(tmp_path / "nonexistent.json")
    assert log.list_transactions() == []


def test_save_then_load_transaction_by_id(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    tx = _tx(tmp_path)
    log.save_transaction(tx)

    loaded = log.load_transaction(tx.transaction_id)

    assert loaded is not None
    assert loaded.transaction_id == tx.transaction_id
    assert loaded.plan_id == "plan-1"
    assert loaded.actions[0].rollback_from == tx.actions[0].new_path
    assert loaded.actions[0].rollback_to == tx.actions[0].original_path


def test_update_transaction_replaces_existing(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    tx = _tx(tmp_path, status="pending")
    log.save_transaction(tx)

    tx.actions[0].status = "success"
    log.update_transaction(tx)

    assert len(log.list_transactions()) == 1, "update 不可新增重複 entry"
    assert log.load_transaction(tx.transaction_id).actions[0].status == "success"


def test_save_transaction_does_not_overwrite_unrelated(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    tx_a = _tx(tmp_path)
    tx_b = MoveTransaction(plan_id="plan-2", actions=[])
    log.save_transaction(tx_a)

    log.save_transaction(tx_b)

    assert len(log.list_transactions()) == 2
    assert log.load_transaction(tx_a.transaction_id) is not None
    assert log.load_transaction(tx_b.transaction_id) is not None


def test_datetime_roundtrip(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    created = datetime(2026, 6, 11, 12, 30, 0, tzinfo=timezone.utc)
    tx = MoveTransaction(plan_id="plan-1", created_at=created, actions=[])
    log.save_transaction(tx)

    loaded = log.load_transaction(tx.transaction_id)

    assert loaded.created_at == created, "datetime 應可無損序列化/反序列化"


# ---------------------------------------------------------------------------
# 測試 7–9：mark_transaction_actions 與 invalid JSON
# ---------------------------------------------------------------------------


def test_mark_transaction_actions_by_original_path(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    tx = _tx(tmp_path, status="pending")
    log.save_transaction(tx)

    updated = log.mark_transaction_actions(
        tx.transaction_id, {tx.actions[0].original_path: "success"}
    )

    assert updated.actions[0].status == "success"
    assert log.load_transaction(tx.transaction_id).actions[0].status == "success"


def test_mark_transaction_actions_by_new_path(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    tx = _tx(tmp_path, status="success")
    log.save_transaction(tx)

    updated = log.mark_transaction_actions(
        tx.transaction_id, {tx.actions[0].new_path: "rolled_back"}
    )

    assert updated.actions[0].status == "rolled_back"


def test_invalid_json_handled_safely(tmp_path):
    log_path = tmp_path / "move_tx.json"
    log_path.write_text("{not valid json!!", encoding="utf-8")
    log = MoveTransactionLog(log_path)

    assert log.list_transactions() == []
    assert log.load_transaction("any-id") is None
    # 仍可正常寫入新 transaction
    tx = _tx(tmp_path)
    log.save_transaction(tx)
    assert log.load_transaction(tx.transaction_id) is not None


# ---------------------------------------------------------------------------
# 測試 10 + 11：build_move_transaction 只收 low/medium
# ---------------------------------------------------------------------------


def test_build_move_transaction_includes_only_low_medium(tmp_path):
    c_low = _tmp_candidate(tmp_path, "low.pdf", create_source=False)
    c_medium = _tmp_candidate(tmp_path, "med.pdf", create_source=False)
    plan = _make_plan([c_low, c_medium], ["low", "medium"])

    tx = build_move_transaction(plan)

    assert len(tx.actions) == 2
    assert all(a.status == "pending" for a in tx.actions)
    assert tx.actions[0].rollback_from == c_low.proposed_path
    assert tx.actions[0].rollback_to == c_low.original_path
    assert tx.plan_id == plan.plan_id


def test_build_move_transaction_excludes_high_and_blocked(tmp_path):
    c_low = _tmp_candidate(tmp_path, "low.pdf", create_source=False)
    c_high = _tmp_candidate(tmp_path, "high.pdf", create_source=False)
    c_blocked = _tmp_candidate(tmp_path, "blocked.pdf", create_source=False)
    plan = _make_plan([c_low, c_high, c_blocked], ["low", "high", "blocked"])

    tx = build_move_transaction(plan)

    assert len(tx.actions) == 1
    assert tx.actions[0].original_path == c_low.original_path


# ---------------------------------------------------------------------------
# 測試 12–14：execute_move_plan 與 transaction_log 整合
# ---------------------------------------------------------------------------


def test_execute_with_transaction_log_persists_transaction(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])
    log = MoveTransactionLog(tmp_path / "logs" / "move_tx.json")

    result = execute_move_plan(plan, transaction_log=log)

    assert result.success_count == 1
    transactions = log.list_transactions()
    assert len(transactions) == 1
    assert transactions[0].plan_id == plan.plan_id
    assert transactions[0].actions[0].rollback_from == c.proposed_path
    assert transactions[0].actions[0].rollback_to == c.original_path


def test_execute_with_transaction_log_updates_action_status(tmp_path):
    c_ok = _tmp_candidate(tmp_path, "ok.pdf")
    c_missing = _tmp_candidate(tmp_path, "ghost.pdf", create_source=False)
    plan = _make_plan([c_ok, c_missing], ["low", "low"])
    log = MoveTransactionLog(tmp_path / "move_tx.json")

    result = execute_move_plan(plan, transaction_log=log)

    assert result.success_count == 1
    assert result.failed_count == 1
    tx = log.list_transactions()[0]
    status_by_orig = {a.original_path: a.status for a in tx.actions}
    assert status_by_orig[c_ok.original_path] == "success"
    assert status_by_orig[c_missing.original_path] == "failed"


def test_execute_without_transaction_log_still_works(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)  # 與 Phase 15D 行為相同

    assert result.success_count == 1
    assert Path(c.proposed_path).exists()
    assert not Path(c.original_path).exists()
    assert result.results[0].rollback_from == c.proposed_path
    assert result.results[0].rollback_to == c.original_path


# ---------------------------------------------------------------------------
# 測試 15–17：rollback_move_transaction
# ---------------------------------------------------------------------------


def _moved_tx(tmp_path: Path) -> MoveTransaction:
    """以 executor 真實搬移一個檔案，回傳對應的 success transaction。"""
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])
    tx = build_move_transaction(plan)
    result = execute_move_plan(plan)
    assert result.success_count == 1
    tx.actions[0].status = "success"
    return tx


def test_rollback_move_transaction_restores_file(tmp_path):
    tx = _moved_tx(tmp_path)
    moved_path = Path(tx.actions[0].rollback_from)
    original_path = Path(tx.actions[0].rollback_to)
    assert moved_path.exists() and not original_path.exists()

    result = rollback_move_transaction(tx)

    assert result.executed is True
    assert result.success_count == 1
    assert result.results[0].reason == "rolled_back"
    assert original_path.exists(), "rollback 應將檔案搬回原位置"
    assert not moved_path.exists()
    assert original_path.read_text() == "content-bill.pdf"


def test_rollback_fails_when_source_missing(tmp_path):
    tx = _tx(tmp_path, status="success")  # rollback_from 實際不存在

    result = rollback_move_transaction(tx)

    assert result.failed_count == 1
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "rollback_source_not_found"


def test_rollback_fails_when_target_exists(tmp_path):
    tx = _moved_tx(tmp_path)
    # 在原位置放一個新檔案，製造 rollback collision
    original_path = Path(tx.actions[0].rollback_to)
    original_path.write_text("occupied")

    result = rollback_move_transaction(tx)

    assert result.failed_count == 1
    assert result.results[0].reason == "rollback_target_already_exists"
    assert original_path.read_text() == "occupied", "rollback 不可覆蓋既有檔案"
    assert Path(tx.actions[0].rollback_from).exists(), "搬移後的檔案應原地保留"


def test_rollback_ignores_non_success_actions(tmp_path):
    tx = _tx(tmp_path, status="pending")
    tx.actions.append(MoveTransactionAction(
        original_path=str(tmp_path / "a.pdf"),
        new_path=str(tmp_path / "b.pdf"),
        status="failed",
        rollback_from=str(tmp_path / "b.pdf"),
        rollback_to=str(tmp_path / "a.pdf"),
    ))

    result = rollback_move_transaction(tx)

    assert result.executed is False, "無 success action 時不應碰 filesystem"
    assert result.results == []


def test_rollback_recreates_missing_original_folder(tmp_path):
    tx = _moved_tx(tmp_path)
    # 模擬原資料夾已被外部清掉
    original_path = Path(tx.actions[0].rollback_to)
    original_path.parent.rmdir()

    result = rollback_move_transaction(tx)

    assert result.success_count == 1
    assert original_path.exists(), "rollback 應自動重建原資料夾"


# ---------------------------------------------------------------------------
# 測試 18–21：rollback_move_transaction_by_id
# ---------------------------------------------------------------------------


def test_rollback_by_id_returns_transaction_not_found(tmp_path):
    log = MoveTransactionLog(tmp_path / "move_tx.json")

    result = rollback_move_transaction_by_id("no-such-id", log)

    assert result.executed is False
    assert result.failed_count == 1
    assert result.results[0].reason == "transaction_not_found"


def test_rollback_by_id_rolls_back_persisted_transaction(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    execute_move_plan(plan, transaction_log=log)
    tx_id = log.list_transactions()[0].transaction_id

    result = rollback_move_transaction_by_id(tx_id, log)

    assert result.success_count == 1
    assert Path(c.original_path).exists(), "檔案應被搬回原位置"
    assert not Path(c.proposed_path).exists()


def test_rollback_by_id_marks_action_rolled_back(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    execute_move_plan(plan, transaction_log=log)
    tx_id = log.list_transactions()[0].transaction_id

    rollback_move_transaction_by_id(tx_id, log)

    tx = log.load_transaction(tx_id)
    assert tx.actions[0].status == "rolled_back"


def test_failed_rollback_does_not_corrupt_log(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])
    log = MoveTransactionLog(tmp_path / "move_tx.json")
    execute_move_plan(plan, transaction_log=log)
    tx_id = log.list_transactions()[0].transaction_id
    # 占用原位置，讓 rollback 失敗
    Path(c.original_path).write_text("occupied")

    result = rollback_move_transaction_by_id(tx_id, log)

    assert result.failed_count == 1
    tx = log.load_transaction(tx_id)
    assert tx is not None, "log 應仍可正常載入"
    assert tx.actions[0].status == "success", (
        "rollback 失敗的 action 應保持 success（檔案仍在新位置）"
    )
    assert Path(c.proposed_path).exists()


# ---------------------------------------------------------------------------
# 測試 22 + 23：Mock LINE 不可觸發 move rollback、無 rollback 指令
# ---------------------------------------------------------------------------


def test_mock_line_has_no_move_rollback_wiring():
    """Phase 15I 起 Mock LINE 有「回滾搬移」明確指令，但只能透過
    rollback_move_transaction_by_id()（safe executor），不可直接接
    executor 的搬移/低階 rollback API、不可引用 MoveTransactionLog。"""
    import scripts.mock_line as mock_line_module

    source = inspect.getsource(mock_line_module)
    assert "execute_move_plan" not in source, "Mock LINE 不可直接呼叫 move executor"
    assert "MoveTransactionLog" not in source, "Mock LINE 不可直接引用 log class"
    # 不可使用非 by_id 的低階 rollback API（by_id 會同步 log 狀態）
    assert "rollback_move_transaction(" not in source, (
        "Mock LINE 只可使用 rollback_move_transaction_by_id()"
    )
    assert "rollback_move_transaction_by_id" in source, (
        "「回滾搬移」必須走 rollback_move_transaction_by_id()"
    )

    # 「回滾搬移」regex 必須 full match（^ 開頭、$ 結尾）
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            pattern = node.args[0].value
            if pattern.lstrip("^").startswith("回滾搬移"):
                assert pattern.startswith("^") and pattern.endswith("$"), (
                    f"move rollback 指令 regex 必須 full match：{pattern}"
                )


def test_mock_line_rollback_command_only_targets_rename(tmp_path):
    """既有「回滾改名」指令只接 rename transaction log，與 move 無關。"""
    from scripts.mock_line import mock_line_payload
    from app.filename.transaction_log import RenameTransactionLog

    rename_log = RenameTransactionLog(tmp_path / "rename_tx.json")
    output = mock_line_payload("回滾改名 no-such-id", transaction_log=rename_log)

    assert "找不到" in output or "不存在" in output or "transaction" in output.lower()


# ---------------------------------------------------------------------------
# 測試 24：AST 驗證真實 move / rollback 只存在 executor modules
# ---------------------------------------------------------------------------


def test_real_move_and_rollback_only_in_executor_modules():
    """app/ 與 scripts/ 下，.rename() / .move() 只允許出現在
    app/filename/executor.py 與 app/folder_intelligence/executor.py
    （含 15E 新增的 transaction_log.py 也不可搬移檔案）。"""
    repo_root = Path(__file__).resolve().parent.parent
    allowed = {
        repo_root / "app" / "filename" / "executor.py",
        repo_root / "app" / "folder_intelligence" / "executor.py",
    }

    offenders: list[str] = []
    for py_file in list((repo_root / "app").rglob("*.py")) + list(
        (repo_root / "scripts").rglob("*.py")
    ):
        if py_file in allowed or "__pycache__" in py_file.parts:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("rename", "move", "renames"):
                    offenders.append(f"{py_file}:{node.lineno} .{node.func.attr}()")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "shutil":
                        offenders.append(f"{py_file}:{node.lineno} import shutil")

    assert offenders == [], (
        "真實 move/rename 只可存在於 executor modules：\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# 測試 25 + 26：既有 executor / rename 模組回歸（完整回歸由整體 pytest 驗證）
# ---------------------------------------------------------------------------


def test_safe_move_executor_gates_unchanged(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"], status="pending_approval")

    result = execute_move_plan(plan, transaction_log=MoveTransactionLog(
        tmp_path / "move_tx.json"
    ))

    assert result.executed is False
    assert all(r.reason == "plan_not_approved" for r in result.results)
    assert Path(c.original_path).exists()
    assert not (tmp_path / "move_tx.json").exists(), (
        "plan gate 失敗時不應建立 transaction log"
    )


def test_rename_transaction_log_still_independent(tmp_path):
    from app.filename.schemas import RenameTransaction
    from app.filename.transaction_log import RenameTransactionLog

    rename_log = RenameTransactionLog(tmp_path / "rename_tx.json")
    rename_log.save_transaction(RenameTransaction(plan_id="r-1", actions=[]))

    move_log = MoveTransactionLog(tmp_path / "move_tx.json")
    move_log.save_transaction(MoveTransaction(plan_id="m-1", actions=[]))

    assert len(rename_log.list_transactions()) == 1
    assert len(move_log.list_transactions()) == 1
    assert rename_log.list_transactions()[0].plan_id == "r-1"
    assert move_log.list_transactions()[0].plan_id == "m-1"
