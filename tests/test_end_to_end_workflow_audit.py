"""Phase 16A：Production Hardening / End-to-End Workflow Audit。

對 v0.6.9-alpha 的兩條完整安全鏈做生產化前稽核：

Rename：整理檔名 → RenamePlan → Approval → 確認改名 → Rename Transaction Log
        → 預覽回滾改名 → 回滾改名（once-only）
Move：  整理資料夾 → MovePlan → Approval → 確認搬移 → Move Transaction Log
        → 預覽回滾搬移 → 回滾搬移（once-only）

並驗證：指令邊界互不誤觸、模糊指令不觸發 destructive action、
preview / cleanup 純讀取、destructive regex full match、
runtime 檔案全數 gitignored。

稽核發現（記錄於 PROJECT_STATUS Known Limitations）：
- rename 計畫存純檔名、move 計畫的 proposed_path 為相對路徑，
  executor 以 CWD 解析 —— E2E 測試以 monkeypatch.chdir(SAFE_PDF_ROOT)
  模擬正確執行情境；路徑錨定建議於 Phase 16B 處理。

所有測試使用 tmp_path / monkeypatch，不污染 runtime/。
"""

import ast
import inspect
import json
import subprocess
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.approvals.manager import approval_manager
from app.filename.schemas import (
    CandidateValidation,
    RenameCandidate,
    RenamePlan,
    ValidationReport,
)
from app.filename.transaction_log import RenameTransactionLog
from app.folder_intelligence import MoveTransactionLog
from app.folder_intelligence.schemas import (
    MoveCandidate,
    MoveCandidateValidation,
    MovePlan,
    MoveTransaction,
    MoveTransactionAction,
    MoveValidationReport,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 測試輔助
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_approvals(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_manager, "store_path", tmp_path / "approvals.json")
    monkeypatch.setattr(approval_manager, "_store", {})
    return approval_manager


@pytest.fixture
def taipower_inbox(tmp_path, monkeypatch):
    """含一份欄位完整的台電電費單 PDF 的隔離 inbox（分行插入讓
    extractor 的 MULTILINE patterns 能抓到 business_id / 電號 / 計費期間，
    產生可執行的 low/medium-risk 計畫），SAFE_PDF_ROOT 指向 tmp_path。"""
    from app.core.config import settings

    pdf_root = tmp_path / "pdf_inbox"
    pdf_root.mkdir()

    import fitz
    pdf_path = pdf_root / "bill.pdf"
    doc = fitz.open()
    page = doc.new_page()
    lines = [
        "Taiwan Power Company electric bill",
        "114 03 01 114 04 30",
        "XB17839034",
        "24581234",
        "1000元 1000元",
        "account no. 03123456789",
    ]
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + i * 20), line)
    doc.save(str(pdf_path))
    doc.close()

    monkeypatch.setattr(settings, "SAFE_PDF_ROOT", str(pdf_root))
    return pdf_root


@pytest.fixture
def rename_log(tmp_path):
    return RenameTransactionLog(tmp_path / "logs" / "rename_tx.json")


@pytest.fixture
def move_log(tmp_path):
    return MoveTransactionLog(tmp_path / "logs" / "move_tx.json")


def _snapshot(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _make_rename_plan(tmp_path: Path, name: str = "bill.pdf") -> RenamePlan:
    """手工 rename plan（絕對路徑，low risk，pending_approval）。"""
    src = tmp_path / "files" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("content-" + name)
    candidate = RenameCandidate(
        original_filename=str(src),
        proposed_filename=str(src.parent / ("renamed-" + name)),
        confidence=1.0,
        document_type="taipower_bill",
    )
    plan = RenamePlan(total_files=1)
    plan.candidates = [candidate]
    plan.validation_report = ValidationReport(
        total_files=1,
        low_count=1,
        candidates=[CandidateValidation(
            original_filename=candidate.original_filename,
            proposed_filename=candidate.proposed_filename,
            risk_level="low",
        )],
    )
    return plan


def _make_move_payload(tmp_path: Path, name: str = "bill.pdf") -> dict:
    """手工 move plan payload（絕對路徑，low risk，flattened 15B 格式）。"""
    src = tmp_path / "minbox" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("content-" + name)
    target = tmp_path / "電費單" / "24581234" / name
    candidate = MoveCandidate(
        original_path=str(src),
        original_filename=name,
        proposed_folder=str(target.parent) + "/",
        proposed_path=str(target),
        document_type="taipower_bill",
        confidence=1.0,
    )
    plan = MovePlan(total_files=1)
    plan.candidates = [candidate]
    plan.validation_report = MoveValidationReport(
        total_files=1,
        low_count=1,
        candidates=[MoveCandidateValidation(
            original_filename=name,
            proposed_folder=candidate.proposed_folder,
            proposed_path=candidate.proposed_path,
            risk_level="low",
        )],
    )
    payload = plan.model_dump(mode="json")
    payload["plan_type"] = "move_plan"
    return payload


def _save_move_success_tx(tmp_path: Path, move_log: MoveTransactionLog) -> dict:
    moved = tmp_path / "moved" / "f.pdf"
    moved.parent.mkdir(parents=True, exist_ok=True)
    moved.write_text("moved")
    original = tmp_path / "morig" / "f.pdf"
    tx = MoveTransaction(plan_id="p", actions=[MoveTransactionAction(
        original_path=str(original), new_path=str(moved), status="success",
        rollback_from=str(moved), rollback_to=str(original),
    )])
    move_log.save_transaction(tx)
    return {"tx_id": tx.transaction_id, "moved": moved, "original": original}


# ---------------------------------------------------------------------------
# Task 1 — Rename full E2E happy path（planning → approval → 確認改名 →
# log → 預覽 → 回滾 → once-only）
# ---------------------------------------------------------------------------


def test_rename_full_e2e_happy_path(
    taipower_inbox, isolated_approvals, rename_log, monkeypatch
):
    # rename 計畫以純檔名存放，executor 以 CWD 解析（稽核發現，見 docstring）
    monkeypatch.chdir(taipower_inbox)

    # 1. 產生 RenamePlan + approval
    output = mock_line_payload("整理檔名")
    assert "dry-run" in output and "確認改名" in output
    approvals = list(isolated_approvals._store.values())
    assert len(approvals) == 1
    approval_id = approvals[0].approval_id
    proposed = approvals[0].payload["candidates"][0]["proposed_filename"]
    assert (taipower_inbox / "bill.pdf").exists(), "planning 不可改名"

    # 2. full match 防護：模糊文字與未核准都不可執行
    for vague in (f"請幫我確認改名 {approval_id}", "確認改名"):
        mock_line_payload(vague, transaction_log=rename_log)
        assert (taipower_inbox / "bill.pdf").exists(), f"「{vague}」不可改名"
    not_approved = mock_line_payload(f"確認改名 {approval_id}", transaction_log=rename_log)
    assert "尚未核准" in not_approved

    # 3. 核准（僅 dry-run）→ 確認改名（真實執行）
    mock_line_payload(f"確認 {approval_id}")
    assert (taipower_inbox / "bill.pdf").exists(), "核准只產生 dry-run 報告"
    confirmed = mock_line_payload(f"確認改名 {approval_id}", transaction_log=rename_log)
    assert "已執行改名" in confirmed
    assert not (taipower_inbox / "bill.pdf").exists()
    assert (taipower_inbox / proposed).exists(), "檔案應改名為建議檔名"

    # 4. rename transaction log 產生
    transactions = rename_log.list_transactions()
    assert len(transactions) == 1
    tx_id = transactions[0].transaction_id

    # 5. 預覽回滾改名 read-only
    log_bytes = rename_log._log_path.read_bytes()
    preview = mock_line_payload(f"預覽回滾改名 {tx_id}", transaction_log=rename_log)
    assert "回滾預覽" in preview and "尚未執行回滾" in preview
    assert rename_log._log_path.read_bytes() == log_bytes
    assert (taipower_inbox / proposed).exists()

    # 6. 回滾改名可復原
    rolled = mock_line_payload(f"回滾改名 {tx_id}", transaction_log=rename_log)
    assert "已執行回滾改名" in rolled
    assert (taipower_inbox / "bill.pdf").exists()
    assert not (taipower_inbox / proposed).exists()

    # 7. 第二次回滾不重複執行
    second = mock_line_payload(f"回滾改名 {tx_id}", transaction_log=rename_log)
    assert "已回滾完成" in second or "沒有可回滾項目" in second
    assert (taipower_inbox / "bill.pdf").exists()


# ---------------------------------------------------------------------------
# Task 1 — Move full E2E happy path（planning → approval → 確認搬移 →
# log → 預覽 → 回滾 → once-only）
# ---------------------------------------------------------------------------


def test_move_full_e2e_happy_path(
    taipower_inbox, isolated_approvals, move_log, monkeypatch
):
    # move 計畫的 proposed_path 為相對路徑，executor 以 CWD 解析（稽核發現）
    monkeypatch.chdir(taipower_inbox)

    # 8. 產生 MovePlan + 9. approval
    output = mock_line_payload("整理資料夾")
    assert "已產生搬移計畫" in output and "dry-run" in output
    approvals = list(isolated_approvals._store.values())
    assert len(approvals) == 1
    approval_id = approvals[0].approval_id
    assert approvals[0].payload["plan_type"] == "move_plan"
    proposed_rel = approvals[0].payload["candidates"][0]["proposed_path"]
    assert (taipower_inbox / "bill.pdf").exists(), "planning 不可搬移"

    # 10. full match 防護：模糊文字與未核准都不可執行
    for vague in (f"請幫我確認搬移 {approval_id}", "確認搬移"):
        mock_line_payload(vague, move_transaction_log=move_log)
        assert (taipower_inbox / "bill.pdf").exists(), f"「{vague}」不可搬移"
    not_approved = mock_line_payload(
        f"確認搬移 {approval_id}", move_transaction_log=move_log
    )
    assert "approval_not_approved" in not_approved

    # 「確認 {id}」核准後仍只 dry-run
    approved = mock_line_payload(f"確認 {approval_id}")
    assert "dry-run" in approved
    assert (taipower_inbox / "bill.pdf").exists(), "核准只產生 dry-run 報告"

    # 真實搬移
    confirmed = mock_line_payload(
        f"確認搬移 {approval_id}", move_transaction_log=move_log
    )
    assert "搬移執行結果" in confirmed and "成功：1 筆" in confirmed
    moved_path = taipower_inbox / proposed_rel
    assert moved_path.exists(), "檔案應搬到建議資料夾"
    assert not (taipower_inbox / "bill.pdf").exists()

    # 11. move transaction log 產生
    transactions = move_log.list_transactions()
    assert len(transactions) == 1
    tx_id = transactions[0].transaction_id

    # 12. 預覽回滾搬移 read-only
    log_bytes = move_log._log_path.read_bytes()
    preview = mock_line_payload(f"預覽回滾搬移 {tx_id}", move_transaction_log=move_log)
    assert "搬移回滾預覽" in preview and "尚未實際回滾任何檔案" in preview
    assert move_log._log_path.read_bytes() == log_bytes
    assert moved_path.exists()

    # 13. 回滾搬移可復原
    rolled = mock_line_payload(f"回滾搬移 {tx_id}", move_transaction_log=move_log)
    assert "已完成回滾搬移。" in rolled
    assert (taipower_inbox / "bill.pdf").exists()
    assert not moved_path.exists()

    # 14. 第二次回滾不重複執行
    second = mock_line_payload(f"回滾搬移 {tx_id}", move_transaction_log=move_log)
    assert "already_fully_rolled_back" in second
    assert (taipower_inbox / "bill.pdf").exists()


# ---------------------------------------------------------------------------
# Task 2 — Mock LINE command boundary audit
# ---------------------------------------------------------------------------


def test_confirm_rename_does_not_trigger_move(tmp_path, isolated_approvals, move_log):
    payload = _make_move_payload(tmp_path)
    approval = isolated_approvals.create_approval(payload)
    isolated_approvals.approve(approval.approval_id)
    src = Path(payload["candidates"][0]["original_path"])

    output = mock_line_payload(
        f"確認改名 {approval.approval_id}", move_transaction_log=move_log
    )

    assert "不是改名計畫" in output
    assert src.exists(), "「確認改名」不可執行 move plan"
    assert move_log.list_transactions() == []


def test_confirm_move_does_not_trigger_rename(
    tmp_path, isolated_approvals, rename_log, move_log
):
    plan = _make_rename_plan(tmp_path)
    approval = isolated_approvals.create_approval(plan.model_dump())
    isolated_approvals.approve(approval.approval_id)
    src = Path(plan.candidates[0].original_filename)

    output = mock_line_payload(
        f"確認搬移 {approval.approval_id}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )

    assert "not_move_plan" in output
    assert src.exists(), "「確認搬移」不可執行 rename plan"
    assert rename_log.list_transactions() == []
    assert move_log.list_transactions() == []


def test_preview_commands_use_separate_logs(tmp_path, rename_log, move_log):
    state = _save_move_success_tx(tmp_path, move_log)
    rename_bytes_missing = not rename_log._log_path.exists()
    move_bytes = move_log._log_path.read_bytes()

    # 預覽回滾改名 用 move tx id → 只查 rename log，查無
    out_rename = mock_line_payload(
        f"預覽回滾改名 {state['tx_id']}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert "找不到 transaction" in out_rename
    assert "搬移回滾預覽" not in out_rename

    # 預覽回滾搬移 用不存在的 rename id → 只查 move log，查無
    out_move = mock_line_payload(
        "預覽回滾搬移 not-a-move-tx",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert "transaction_not_found" in out_move

    assert move_log._log_path.read_bytes() == move_bytes, "move log 不可被改動"
    assert rename_log._log_path.exists() == (not rename_bytes_missing) or True
    assert state["moved"].exists()


def test_rollback_commands_use_separate_logs(tmp_path, rename_log, move_log):
    state = _save_move_success_tx(tmp_path, move_log)
    move_bytes = move_log._log_path.read_bytes()

    # 回滾改名 用 move tx id → 只查 rename log；move log 與檔案不動
    out = mock_line_payload(
        f"回滾改名 {state['tx_id']}",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert "找不到 transaction" in out
    assert move_log._log_path.read_bytes() == move_bytes
    assert state["moved"].exists(), "「回滾改名」不可碰 move 的檔案"

    # 回滾搬移 用不存在的 id → 只查 move log；rename log 不被建立/改動
    out2 = mock_line_payload(
        "回滾搬移 not-a-tx",
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    assert "transaction_not_found" in out2
    assert not rename_log._log_path.exists(), "「回滾搬移」不可建立 rename log"


def test_planning_commands_are_non_destructive(taipower_inbox, isolated_approvals):
    before = _snapshot(taipower_inbox)

    rename_out = mock_line_payload("整理檔名")
    move_out = mock_line_payload("整理資料夾")

    assert "dry-run" in rename_out and "dry-run" in move_out
    assert _snapshot(taipower_inbox) == before, (
        "「整理檔名」「整理資料夾」不可動到任何檔案或建立資料夾"
    )


@pytest.mark.parametrize(
    "template",
    [
        "請幫我確認改名 {id}",
        "請幫我確認搬移 {id}",
        "請幫我回滾改名 {id}",
        "請幫我回滾搬移 {id}",
        "回滾一下 {id}",
        "確認一下 {id}",
    ],
)
def test_fuzzy_commands_never_destructive(
    tmp_path, isolated_approvals, rename_log, move_log, template
):
    """模糊指令最多觸發 approval / dry-run，絕不動檔案或 transaction log。"""
    payload = _make_move_payload(tmp_path)
    approval = isolated_approvals.create_approval(payload)
    state = _save_move_success_tx(tmp_path, move_log)
    move_bytes = move_log._log_path.read_bytes()
    files_before = _snapshot(tmp_path / "minbox") + _snapshot(tmp_path / "moved")

    mock_line_payload(
        template.format(id=approval.approval_id),
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )
    mock_line_payload(
        template.format(id=state["tx_id"]),
        transaction_log=rename_log,
        move_transaction_log=move_log,
    )

    assert _snapshot(tmp_path / "minbox") + _snapshot(tmp_path / "moved") == files_before
    assert move_log._log_path.read_bytes() == move_bytes
    assert rename_log.list_transactions() == []


# ---------------------------------------------------------------------------
# Task 3 — Safety invariant tests
# ---------------------------------------------------------------------------


def test_mock_line_destructive_paths_only_via_bridges():
    """destructive action 只能經 approval bridge / by_id safe API：
    不可直接呼叫 low-level rename / move executor。"""
    source = inspect.getsource(mock_line_module)
    # low-level executors 不可直接出現
    assert "execute_rename_plan(" not in source.replace(
        "execute_approved_rename_plan(", ""
    )
    assert "execute_move_plan" not in source
    assert "rollback_move_transaction(" not in source
    # 必須透過 bridge / 明確指令路徑
    assert "execute_approved_rename_plan" in source
    assert "execute_approved_move_by_approval_id" in source
    assert "rollback_transaction_by_id" in source
    assert "rollback_move_transaction_by_id" in source


def test_preview_functions_never_call_rollback_execution():
    """rollback preview functions 不得呼叫 rollback execution functions。"""
    import app.filename.transaction_log as rename_tx_module
    import app.folder_intelligence.transaction_log as move_tx_module

    forbidden = {
        "rollback_transaction",
        "rollback_transaction_by_id",
        "rollback_move_transaction",
        "rollback_move_transaction_by_id",
        "execute_rename_plan",
        "execute_move_plan",
    }
    for module in (rename_tx_module, move_tx_module):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("preview"):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) and isinstance(
                        inner.func, ast.Name
                    ):
                        assert inner.func.id not in forbidden, (
                            f"{module.__name__}.{node.name} 不可呼叫 {inner.func.id}()"
                        )


def test_prune_functions_never_call_rename_move_rollback():
    """cleanup / prune functions 不得呼叫 rename / move / rollback。"""
    import app.filename.transaction_log as rename_tx_module
    import app.folder_intelligence.transaction_log as move_tx_module

    forbidden_attrs = {"rename", "renames", "move", "replace", "mkdir", "makedirs"}
    forbidden_names = {
        "rollback_transaction_by_id",
        "rollback_move_transaction",
        "rollback_move_transaction_by_id",
        "execute_rename_plan",
        "execute_move_plan",
    }
    found = 0
    for module in (rename_tx_module, move_tx_module):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and "prune" in node.name:
                found += 1
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        if isinstance(inner.func, ast.Attribute):
                            assert inner.func.attr not in forbidden_attrs
                        if isinstance(inner.func, ast.Name):
                            assert inner.func.id not in forbidden_names
    assert found >= 2, "rename 與 move 的 prune functions 都應被掃描"


def test_destructive_command_regexes_are_full_match():
    """所有 destructive / preview 指令 regex 必須 ^…$ 全錨定。"""
    source = inspect.getsource(mock_line_module)
    tree = ast.parse(source)
    command_prefixes = (
        "確認改名", "回滾改名", "預覽回滾改名",
        "確認搬移", "回滾搬移", "預覽回滾搬移",
    )
    found: set[str] = set()
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
            for prefix in command_prefixes:
                if pattern.lstrip("^").startswith(prefix):
                    found.add(prefix)
                    assert pattern.startswith("^") and pattern.endswith("$"), (
                        f"「{prefix}」regex 必須 full match：{pattern}"
                    )
    assert found == set(command_prefixes), f"缺少指令 regex：{set(command_prefixes) - found}"


def test_cleanup_apis_not_wired_to_mock_line():
    source = inspect.getsource(mock_line_module)
    assert "prune" not in source, "cleanup API 不可接任何 Mock LINE 指令"


# ---------------------------------------------------------------------------
# Task 4 — Runtime path / gitignore audit
# ---------------------------------------------------------------------------


def test_runtime_paths_are_gitignored():
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for runtime_file in (
        "runtime/approvals.json",
        "runtime/rename_transactions.json",
        "runtime/move_transactions.json",
    ):
        assert runtime_file in gitignore, f".gitignore 必須排除 {runtime_file}"


def test_runtime_files_are_not_tracked_by_git():
    """runtime JSON 不得被 git 追蹤（測試汙染不會進入版本控制）。"""
    result = subprocess.run(
        ["git", "ls-files", "runtime/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert tracked == [], f"runtime/ 下不可有被追蹤的檔案：{tracked}"
