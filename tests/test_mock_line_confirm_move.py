"""Phase 15G 測試：Explicit Mock LINE Confirm Move Command。

「確認搬移 {approval_id}」是唯一可觸發真實搬移的 Mock LINE 指令：

- regex full match 才生效；「確認」「搬移」「確認搬移」「確認搬移一下 …」
  「請幫我確認搬移 …」「整理資料夾」「產生搬移計畫」「確認改名」均不觸發
- 執行一律透過 execute_approved_move_by_approval_id()（move approval
  bridge），Mock LINE 不直接呼叫 move executor
- once-only guard：同一 approval_id 不會重複搬移、不會新增第二筆 transaction
- 沒有任何 move rollback 指令（「回滾搬移」「預覽回滾搬移」不存在）

所有真實搬移測試一律使用 pytest tmp_path；approval store 與
move transaction log 均隔離，不污染 runtime/。
"""

import ast
import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.approvals.manager import approval_manager
from app.folder_intelligence import MoveTransactionLog
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveValidationReport,
)


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    """將全域 approval_manager 隔離到 tmp_path，避免污染 runtime/approvals.json。"""
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


@pytest.fixture
def move_log(tmp_path):
    """tmp_path 下的 move transaction log，避免污染 runtime/move_transactions.json。"""
    return MoveTransactionLog(tmp_path / "log" / "move_transactions.json")


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


def _make_plan(candidates: list[MoveCandidate], risk_levels: list[str]) -> MovePlan:
    plan = MovePlan(total_files=len(candidates), status="pending_approval")
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
    payload = plan.model_dump(mode="json")
    payload["plan_type"] = "move_plan"
    return payload


def _approved_move_approval(manager, plan: MovePlan) -> str:
    approval = manager.create_approval(_flattened_payload(plan))
    manager.approve(approval.approval_id)
    return approval.approval_id


@pytest.fixture
def bridge_spy(monkeypatch):
    """側錄 mock_line 對 move approval bridge 的呼叫。"""
    calls: list[str] = []
    real = mock_line_module.execute_approved_move_by_approval_id

    def _spy(approval_id, manager, transaction_log=None):
        calls.append(approval_id)
        return real(approval_id, manager, transaction_log=transaction_log)

    monkeypatch.setattr(
        mock_line_module, "execute_approved_move_by_approval_id", _spy
    )
    return calls


# ---------------------------------------------------------------------------
# 測試 1–3：明確指令觸發 bridge、真實搬移、transaction log
# ---------------------------------------------------------------------------


def test_exact_confirm_move_triggers_move_approval_bridge(
    tmp_path, isolated_approvals, move_log, bridge_spy
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert bridge_spy == [approval_id], "「確認搬移」必須走 move approval bridge"


def test_exact_command_moves_low_risk_file_using_tmp_path(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert not Path(candidate.original_path).exists()
    moved = Path(candidate.proposed_path)
    assert moved.exists()
    assert moved.read_text() == "content-bill.pdf"
    assert "成功：1 筆" in output


def test_exact_command_creates_move_transaction_log(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    transactions = move_log.list_transactions()
    assert len(transactions) == 1
    assert transactions[0].plan_id == plan.plan_id
    assert transactions[0].actions[0].status == "success"


# ---------------------------------------------------------------------------
# 測試 4–8：response 格式
# ---------------------------------------------------------------------------


def test_response_includes_title_and_flags(tmp_path, isolated_approvals, move_log):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "搬移執行結果" in output
    assert "executed：True" in output
    assert "dry_run：False" in output


def test_response_includes_all_counts(tmp_path, isolated_approvals, move_log):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "總數：1 筆" in output
    assert "成功：1 筆" in output
    assert "失敗：0 筆" in output
    assert "跳過：0 筆" in output
    assert "blocked：0 筆" in output


def test_response_includes_transaction_id(tmp_path, isolated_approvals, move_log):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    tx_id = move_log.list_transactions()[0].transaction_id
    assert f"transaction_id：{tx_id}" in output


def test_response_includes_rollback_paths_for_success(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert f"rollback_from：{candidate.proposed_path}" in output
    assert f"rollback_to：{candidate.original_path}" in output


def test_response_warns_rollback_command_not_available(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "已建立 rollback 資訊" in output
    assert "尚未開放" in output


# ---------------------------------------------------------------------------
# 測試 9–13：模糊／不完整指令不可觸發真實搬移（full match only）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template",
    [
        "搬移 {approval_id}",
        "確認搬移",
        "確認搬移一下 {approval_id}",
        "請幫我確認搬移 {approval_id}",
    ],
)
def test_fuzzy_commands_do_not_trigger_move(
    tmp_path, isolated_approvals, move_log, bridge_spy, template
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    mock_line_payload(
        template.format(approval_id=approval_id), move_transaction_log=move_log
    )

    assert bridge_spy == [], f"「{template}」不可觸發 move bridge"
    assert Path(candidate.original_path).exists(), "檔案不可被搬移"
    assert not Path(candidate.proposed_path).exists()
    assert move_log.list_transactions() == []


def test_plain_confirm_does_not_trigger_move(
    tmp_path, isolated_approvals, move_log, bridge_spy
):
    """「確認 {approval_id}」只核准並顯示 dry-run 報告，不搬移。"""
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = isolated_approvals.create_approval(_flattened_payload(plan))  # pending

    mock_line_payload(f"確認 {approval.approval_id}", move_transaction_log=move_log)

    assert bridge_spy == [], "「確認」不可觸發 move bridge"
    assert Path(candidate.original_path).exists(), "檔案不可被搬移"
    assert not Path(candidate.proposed_path).exists()
    assert move_log.list_transactions() == []


# ---------------------------------------------------------------------------
# 測試 14–15：planning 指令仍只產生 dry-run plan，不搬移
# ---------------------------------------------------------------------------


def test_planning_keywords_still_only_generate_dry_run_plan(
    tmp_path, isolated_approvals, monkeypatch, bridge_spy
):
    from app.core.config import settings

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()

    import fitz

    pdf_path = pdf_root / "bill.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Taiwan Power Company electric bill amount due 1000")
    doc.save(str(pdf_path))
    doc.close()

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))

    for keyword in ["整理資料夾", "產生搬移計畫"]:
        output = mock_line_payload(keyword)
        assert "已產生搬移計畫" in output
        assert "dry-run" in output
        assert pdf_path.exists(), f"「{keyword}」不可搬移原始 PDF"
        subdirs = [p for p in pdf_root.iterdir() if p.is_dir()]
        assert subdirs == [], f"「{keyword}」不可建立資料夾：{subdirs}"

    assert bridge_spy == [], "planning 指令不可觸發 move bridge"


# ---------------------------------------------------------------------------
# 測試 16：「確認改名」不可執行 move plan
# ---------------------------------------------------------------------------


def test_confirm_rename_does_not_trigger_move(
    tmp_path, isolated_approvals, move_log, bridge_spy
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(
        f"確認改名 {approval_id}",
        transaction_log=None,
        move_transaction_log=move_log,
    )

    assert "不是改名計畫" in output
    assert bridge_spy == []
    assert Path(candidate.original_path).exists(), "檔案不可被搬移"
    assert move_log.list_transactions() == []


# ---------------------------------------------------------------------------
# 測試 17–18：move rollback 指令不存在
# ---------------------------------------------------------------------------


def test_move_rollback_commands_do_not_exist(tmp_path, isolated_approvals, move_log):
    """「回滾搬移」不是指令；「預覽回滾搬移」（15H）為 read-only 預覽：
    兩者都不可動檔案 —— 成功搬移後檔案保持在新位置，
    transaction log 的 action 狀態不變。"""
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)
    mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)
    tx_id = move_log.list_transactions()[0].transaction_id

    for command in (f"回滾搬移 {tx_id}", f"預覽回滾搬移 {tx_id}"):
        mock_line_payload(command, move_transaction_log=move_log)
        assert Path(candidate.proposed_path).exists(), (
            f"「{command}」不可回滾搬移（檔案應留在新位置）"
        )
        assert not Path(candidate.original_path).exists()
        assert move_log.list_transactions()[0].actions[0].status == "success", (
            "log 狀態不可被改動"
        )


# ---------------------------------------------------------------------------
# 測試 19–20：once-only guard
# ---------------------------------------------------------------------------


def test_repeated_confirm_move_does_not_move_twice(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    first = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)
    assert "成功：1 筆" in first

    # 在原位置放新檔案：若 guard 失效，第二次會試圖再搬移它
    src = Path(candidate.original_path)
    src.write_text("new-unrelated-content")

    second = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "already_executed" in second
    assert "已執行過" in second
    assert src.exists() and src.read_text() == "new-unrelated-content", (
        "第二次「確認搬移」不可搬移任何檔案"
    )


def test_repeated_confirm_move_does_not_create_second_transaction(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)
    mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert len(move_log.list_transactions()) == 1, "不可新增第二筆 transaction"


# ---------------------------------------------------------------------------
# 測試 21–23：approval-level gates 的回覆
# ---------------------------------------------------------------------------


def test_not_approved_approval_returns_approval_not_approved(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["low"])
    approval = isolated_approvals.create_approval(_flattened_payload(plan))  # pending

    output = mock_line_payload(
        f"確認搬移 {approval.approval_id}", move_transaction_log=move_log
    )

    assert "approval_not_approved" in output
    assert "尚未核准" in output
    assert Path(candidate.original_path).exists()
    assert move_log.list_transactions() == []


def test_missing_approval_returns_approval_not_found(isolated_approvals, move_log):
    output = mock_line_payload("確認搬移 no-such-id", move_transaction_log=move_log)

    assert "approval_not_found" in output
    assert "找不到 approval" in output


def test_non_move_approval_returns_not_move_plan(
    tmp_path, isolated_approvals, move_log
):
    approval = isolated_approvals.create_approval(
        {"plan_id": "r-1", "candidates": []}  # rename 風格 payload，無 plan_type
    )
    isolated_approvals.approve(approval.approval_id)

    output = mock_line_payload(
        f"確認搬移 {approval.approval_id}", move_transaction_log=move_log
    )

    assert "not_move_plan" in output
    assert "不是搬移計畫" in output
    assert move_log.list_transactions() == []


# ---------------------------------------------------------------------------
# 測試 24–26：executor 安全規則在指令路徑下仍生效
# ---------------------------------------------------------------------------


def test_target_collision_does_not_overwrite(tmp_path, isolated_approvals, move_log):
    candidate = _tmp_candidate(tmp_path)
    target = Path(candidate.proposed_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pre-existing")
    plan = _make_plan([candidate], ["low"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "target_file_already_exists" in output
    assert Path(candidate.original_path).exists()
    assert target.read_text() == "pre-existing", "不可覆寫既有檔案"


def test_high_risk_candidate_is_skipped(tmp_path, isolated_approvals, move_log):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["high"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "跳過：1 筆" in output
    assert "high_risk_requires_manual_review" in output
    assert Path(candidate.original_path).exists()
    assert not Path(candidate.proposed_path).exists()


def test_blocked_validation_report_prevents_execution(
    tmp_path, isolated_approvals, move_log
):
    candidate = _tmp_candidate(tmp_path)
    plan = _make_plan([candidate], ["blocked"])
    approval_id = _approved_move_approval(isolated_approvals, plan)

    output = mock_line_payload(f"確認搬移 {approval_id}", move_transaction_log=move_log)

    assert "executed：False" in output
    assert Path(candidate.original_path).exists()
    assert not Path(candidate.proposed_path).exists()


# ---------------------------------------------------------------------------
# 測試 27–28：safety scanning（import / regex 檢查）
# ---------------------------------------------------------------------------


def test_mock_line_imports_bridge_but_not_executor_or_rollback():
    source = inspect.getsource(mock_line_module)
    # 必須透過 bridge 與 default log helper
    assert "execute_approved_move_by_approval_id" in source
    assert "default_move_transaction_log" in source

    # 不可 import executor / rollback API
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    for forbidden in (
        "execute_move_plan",
        "rollback_move_transaction",
        "rollback_move_transaction_by_id",
    ):
        assert forbidden not in imported, f"Mock LINE 不可 import {forbidden}"


def test_mock_line_has_no_move_rollback_regex():
    """「回滾搬移」不可成為可執行指令 regex（15H 起 read-only
    「預覽回滾搬移」regex 是允許的；提示訊息提及尚未開放也允許）。"""
    source = inspect.getsource(mock_line_module)
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
            assert not pattern.lstrip("^").startswith("回滾搬移"), (
                f"Mock LINE 不可有真實 move rollback 指令 regex：{pattern}"
            )
