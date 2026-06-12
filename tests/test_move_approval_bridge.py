"""Phase 15F 測試：Move Approval-to-Execution Bridge。

execute_approved_move_plan() / execute_approved_move_by_approval_id() 是
底層 bridge（仿照 rename 的 14D-1）：

- payload 必須標記 plan_type == "move_plan"
- 支援 nested plan dict 與 15B 扁平 payload 兩種格式
- 還原後將 plan.status 同步為 "approved"，再交給 execute_move_plan()
- approval_id bridge 檢查 approval 存在 / 已核准 / 未執行過（once-only）
- 成功執行後透過 approval_manager.mark_executed() 回寫
  execution_status / executed_at / execution_transaction_id
- 未接任何 Mock LINE 指令；沒有「確認搬移」、沒有 move rollback 指令

所有真實搬移測試一律使用 pytest tmp_path；approval store 與
transaction log 均隔離，不污染 runtime/。
"""

import ast
import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
import app.folder_intelligence.approval_bridge as bridge_module
from app.approvals.manager import ApprovalManager
from app.folder_intelligence import (
    MoveTransactionLog,
    execute_approved_move_by_approval_id,
    execute_approved_move_plan,
)
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveValidationReport,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


def _candidate(
    name: str,
    original_path: str,
    proposed_path: str,
    proposed_folder: str | None = None,
) -> MoveCandidate:
    if proposed_folder is None:
        proposed_folder = str(Path(proposed_path).parent) + "/"
    return MoveCandidate(
        original_path=original_path,
        original_filename=name,
        proposed_folder=proposed_folder,
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
    """建立 tmp_path 下的 candidate，預設會建立 source 檔案。"""
    src = tmp_path / "inbox" / name
    if create_source:
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("content-" + name)
    target = tmp_path / target_subdir / name
    return _candidate(name, str(src), str(target))


def _make_plan(
    candidates: list[MoveCandidate],
    risk_levels: list[str],
    status: str = "pending_approval",
) -> MovePlan:
    """建立帶有完整 MoveValidationReport 的 MovePlan（預設未核准，
    模擬 approval payload 的原始序列化狀態）。"""
    plan = MovePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)
    plan.validation_report = MoveValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=sum(1 for r in risk_levels if r == "blocked"),
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


def _flattened_payload(plan: MovePlan) -> dict:
    """Phase 15B router 格式：plan.model_dump() + plan_type 標記。"""
    payload = plan.model_dump(mode="json")
    payload["plan_type"] = "move_plan"
    return payload


def _nested_payload(plan: MovePlan) -> dict:
    return {"plan_type": "move_plan", "plan": plan.model_dump(mode="json")}


@pytest.fixture
def manager(tmp_path) -> ApprovalManager:
    """隔離的 approval manager，不污染 runtime/approvals.json。"""
    return ApprovalManager(store_path=tmp_path / "approvals.json")


def _approved_move_approval(manager: ApprovalManager, payload: dict):
    approval = manager.create_approval(payload)
    manager.approve(approval.approval_id)
    return manager.get(approval.approval_id)


# ---------------------------------------------------------------------------
# 測試 1–2：payload 型別 gate
# ---------------------------------------------------------------------------


def test_rejects_non_move_payload(tmp_path):
    """非 move_plan payload → not_move_plan，不執行。"""
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    payload = plan.model_dump(mode="json")  # 無 plan_type 標記（如 rename plan）

    result = execute_approved_move_plan(payload)

    assert result.executed is False
    assert result.success_count == 0
    assert result.results[0].reason == "not_move_plan"
    assert Path(candidate.original_path).exists()


def test_rejects_invalid_payload():
    """plan_type 正確但無法還原 MovePlan → invalid_move_plan_payload。"""
    result = execute_approved_move_plan({"plan_type": "move_plan"})

    assert result.executed is False
    assert result.success_count == 0
    assert result.results[0].reason == "invalid_move_plan_payload"


# ---------------------------------------------------------------------------
# 測試 3–6：payload 還原與真實搬移（tmp_path）
# ---------------------------------------------------------------------------


def test_restores_plan_from_nested_plan_dict(tmp_path):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])

    result = execute_approved_move_plan(_nested_payload(plan))

    assert result.executed is True
    assert result.success_count == 1
    assert result.plan_id == plan.plan_id
    assert not Path(candidate.original_path).exists()
    assert Path(candidate.proposed_path).exists()


def test_restores_plan_from_flattened_payload(tmp_path):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])

    result = execute_approved_move_plan(_flattened_payload(plan))

    assert result.executed is True
    assert result.success_count == 1
    assert result.plan_id == plan.plan_id
    assert not Path(candidate.original_path).exists()
    assert Path(candidate.proposed_path).exists()


def test_sets_plan_status_to_approved(tmp_path, monkeypatch):
    """payload 內的 status 為 pending_approval，bridge 須同步為 approved。"""
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"], status="pending_approval")

    captured: dict = {}
    real_execute = bridge_module.execute_move_plan

    def _spy(plan_arg, transaction_log=None):
        captured["status"] = plan_arg.status
        captured["candidate_count"] = len(plan_arg.candidates)
        captured["has_validation_report"] = plan_arg.validation_report is not None
        return real_execute(plan_arg, transaction_log=transaction_log)

    monkeypatch.setattr(bridge_module, "execute_move_plan", _spy)

    result = execute_approved_move_plan(_flattened_payload(plan))

    assert captured["status"] == "approved"
    assert captured["candidate_count"] == 1  # 不破壞原始 candidates
    assert captured["has_validation_report"] is True  # 保留 validation_report
    assert result.success_count == 1


def test_moves_low_risk_file_using_tmp_path(tmp_path):
    candidate = _tmp_candidate(tmp_path, name="taipower-2026-05.pdf")
    plan = _make_plan([candidate], ["low"])

    result = execute_approved_move_plan(_flattened_payload(plan))

    assert result.executed is True
    assert result.success_count == 1
    moved = Path(candidate.proposed_path)
    assert moved.exists()
    assert moved.read_text() == "content-taipower-2026-05.pdf"


# ---------------------------------------------------------------------------
# 測試 7–8：transaction log 整合
# ---------------------------------------------------------------------------


def test_with_transaction_log_persists_transaction(tmp_path):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    log = MoveTransactionLog(tmp_path / "log" / "move_transactions.json")

    result = execute_approved_move_plan(_flattened_payload(plan), transaction_log=log)

    assert result.success_count == 1
    transactions = log.list_transactions()
    assert len(transactions) == 1
    assert transactions[0].plan_id == plan.plan_id
    assert transactions[0].actions[0].status == "success"
    assert transactions[0].actions[0].rollback_to == candidate.original_path


def test_without_transaction_log_still_works(tmp_path):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])

    result = execute_approved_move_plan(_flattened_payload(plan))

    assert result.executed is True
    assert result.success_count == 1
    assert Path(candidate.proposed_path).exists()


# ---------------------------------------------------------------------------
# 測試 9–12：approval_id bridge gates
# ---------------------------------------------------------------------------


def test_by_approval_id_returns_approval_not_found(manager):
    result = execute_approved_move_by_approval_id("no-such-id", manager)

    assert result.executed is False
    assert result.success_count == 0
    assert result.results[0].reason == "approval_not_found"


def test_by_approval_id_rejects_non_move_approval(tmp_path, manager):
    """rename plan 風格的 payload（無 plan_type=move_plan）→ not_move_plan。"""
    approval = manager.create_approval({"plan_id": "r-1", "candidates": []})
    manager.approve(approval.approval_id)

    result = execute_approved_move_by_approval_id(approval.approval_id, manager)

    assert result.executed is False
    assert result.results[0].reason == "not_move_plan"


def test_by_approval_id_rejects_not_approved_approval(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = manager.create_approval(_flattened_payload(plan))  # 仍 pending

    result = execute_approved_move_by_approval_id(approval.approval_id, manager)

    assert result.executed is False
    assert result.results[0].reason == "approval_not_approved"
    assert Path(candidate.original_path).exists()
    assert not Path(candidate.proposed_path).exists()


def test_by_approval_id_executes_approved_move_plan(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))

    result = execute_approved_move_by_approval_id(approval.approval_id, manager)

    assert result.executed is True
    assert result.success_count == 1
    assert not Path(candidate.original_path).exists()
    assert Path(candidate.proposed_path).exists()


# ---------------------------------------------------------------------------
# 測試 13–15：execution_status 回寫
# ---------------------------------------------------------------------------


def test_by_approval_id_records_execution_status(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))

    execute_approved_move_by_approval_id(approval.approval_id, manager)

    refreshed = manager.get(approval.approval_id)
    assert refreshed.payload["execution_status"] == "executed"


def test_by_approval_id_records_executed_at(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))

    execute_approved_move_by_approval_id(approval.approval_id, manager)

    refreshed = manager.get(approval.approval_id)
    assert refreshed.payload.get("executed_at")


def test_by_approval_id_records_execution_transaction_id(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))
    log = MoveTransactionLog(tmp_path / "log" / "move_transactions.json")

    execute_approved_move_by_approval_id(
        approval.approval_id, manager, transaction_log=log
    )

    refreshed = manager.get(approval.approval_id)
    transactions = log.list_transactions()
    assert len(transactions) == 1
    assert (
        refreshed.payload["execution_transaction_id"]
        == transactions[0].transaction_id
    )


# ---------------------------------------------------------------------------
# 測試 16–17：once-only guard
# ---------------------------------------------------------------------------


def test_by_approval_id_does_not_execute_twice(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))
    log = MoveTransactionLog(tmp_path / "log" / "move_transactions.json")

    first = execute_approved_move_by_approval_id(
        approval.approval_id, manager, transaction_log=log
    )
    second = execute_approved_move_by_approval_id(
        approval.approval_id, manager, transaction_log=log
    )

    assert first.success_count == 1
    assert second.executed is False
    assert second.success_count == 0
    assert second.results[0].reason == "already_executed"


def test_repeated_approval_execution_does_not_move_again(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))
    log = MoveTransactionLog(tmp_path / "log" / "move_transactions.json")

    execute_approved_move_by_approval_id(
        approval.approval_id, manager, transaction_log=log
    )

    # 在原位置放一個新檔案：若 guard 失效，第二次呼叫會試圖再搬移它。
    src = Path(candidate.original_path)
    src.write_text("new-unrelated-content")

    second = execute_approved_move_by_approval_id(
        approval.approval_id, manager, transaction_log=log
    )

    assert second.executed is False
    assert src.exists()
    assert src.read_text() == "new-unrelated-content"
    assert len(log.list_transactions()) == 1  # 沒有新增 transaction


# ---------------------------------------------------------------------------
# 測試 18–20：executor 安全規則仍然生效
# ---------------------------------------------------------------------------


def test_high_risk_candidate_still_skipped(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["high"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))

    result = execute_approved_move_by_approval_id(approval.approval_id, manager)

    assert result.success_count == 0
    assert result.skipped_count == 1
    assert result.results[0].reason == "high_risk_requires_manual_review"
    assert Path(candidate.original_path).exists()
    assert not Path(candidate.proposed_path).exists()
    # 沒有任何成功搬移 → 不應標記 executed
    refreshed = manager.get(approval.approval_id)
    assert refreshed.payload.get("execution_status") != "executed"


def test_blocked_validation_report_still_rejected(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["blocked"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))

    result = execute_approved_move_by_approval_id(approval.approval_id, manager)

    assert result.executed is False
    assert result.success_count == 0
    assert Path(candidate.original_path).exists()
    assert not Path(candidate.proposed_path).exists()


def test_target_collision_still_rejected(tmp_path, manager):
    candidate = _tmp_candidate(tmp_path)
    target = Path(candidate.proposed_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pre-existing")
    plan = _make_plan([candidate], ["low"])
    approval = _approved_move_approval(manager, _flattened_payload(plan))

    result = execute_approved_move_by_approval_id(approval.approval_id, manager)

    assert result.success_count == 0
    assert result.results[0].reason == "target_file_already_exists"
    assert Path(candidate.original_path).exists()
    assert target.read_text() == "pre-existing"  # 不覆寫既有檔案


# ---------------------------------------------------------------------------
# 測試 21–23：Mock LINE 隔離（15F 不接任何指令）
# ---------------------------------------------------------------------------


def test_mock_line_uses_bridge_not_executor():
    """Phase 15G 起 Mock LINE 透過「確認搬移」呼叫 approval_id bridge；
    15I 起「回滾搬移」走 rollback_move_transaction_by_id()；
    但不可直接接 executor、低階 rollback API 或 payload-level bridge。"""
    source = inspect.getsource(mock_line_module)
    assert "execute_approved_move_by_approval_id" in source  # 15G 唯一執行路徑
    assert "execute_approved_move_plan" not in source  # payload-level bridge 不直接接
    assert "execute_move_plan" not in source
    assert "rollback_move_transaction_by_id" in source  # 15I 唯一 rollback 路徑
    assert "rollback_move_transaction(" not in source  # 非 by_id 低階 API 不可用
    assert "MoveTransactionLog" not in source


def test_mock_line_move_rollback_regex_is_full_match():
    """15I 起允許「回滾搬移」真實 rollback 指令 regex，但必須 full match
    （^ 開頭、$ 結尾），模糊文字不可觸發。"""
    source = inspect.getsource(mock_line_module)
    tree = ast.parse(source)
    found = False
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
                found = True
                assert pattern.startswith("^") and pattern.endswith("$"), (
                    f"move rollback 指令 regex 必須 full match：{pattern}"
                )
    assert found, "15I 應有「回滾搬移」指令 regex"


def test_bridge_module_never_touches_filesystem_ast():
    """AST 驗證：bridge 模組不直接呼叫 rename/move/replace/mkdir，
    一律委派 execute_move_plan()。"""
    source = inspect.getsource(bridge_module)
    tree = ast.parse(source)
    forbidden = {"rename", "move", "replace", "mkdir", "makedirs", "copy", "copy2"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden, (
                f"approval_bridge 不可直接呼叫 {node.func.attr}()"
            )
