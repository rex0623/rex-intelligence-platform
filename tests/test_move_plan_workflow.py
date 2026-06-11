"""Phase 15B 測試：MovePlan Approval + Dry-run Workflow Integration。

Mock LINE move planning 指令只產生 MovePlan + approval + dry-run summary：
- 不搬移檔案、不建立資料夾
- 沒有真實 move executor
- 沒有「確認搬移」指令
"""

import asyncio
import inspect
from pathlib import Path

import pytest

import scripts.mock_line as mock_line_module
from scripts.mock_line import mock_line_payload
from app.approvals.manager import approval_manager
from app.router.ai_router import AIRouter


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
def taipower_inbox(tmp_path, monkeypatch):
    """建立含一份台電電費單 PDF 的隔離 inbox，並指向 SAFE_PDF_ROOT。"""
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
    return pdf_root


def _snapshot(root: Path) -> list[str]:
    """遞迴快照目錄內容（含子資料夾），用於驗證沒有任何檔案被動到。"""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# ---------------------------------------------------------------------------
# 測試 1–4：router intent 辨識
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["整理資料夾", "產生搬移計畫", "分析 PDF 並產生搬移計畫", "產生資料夾歸檔計畫"],
)
def test_router_detects_move_planning_intent(text):
    assert AIRouter()._detect_intent(text) == "move_planning"


def test_router_existing_intents_not_broken():
    router = AIRouter()
    assert router._detect_intent("整理檔名") == "rename_planning"
    assert router._detect_intent("產生改名計畫") == "rename_planning"
    assert router._detect_intent("分析 PDF 並產生改名計畫") == "rename_planning"
    assert router._detect_intent("整理 Downloads") == "file_management"
    assert router._select_worker("move_planning") == "pdf_worker"


# ---------------------------------------------------------------------------
# 測試 5 + 6：worker generate_move_plan 產生 MovePlan 並掛 validation_report
# ---------------------------------------------------------------------------


def test_worker_generate_move_plan(taipower_inbox):
    from app.workers.pdf_worker import PDFWorker

    result = asyncio.run(PDFWorker().generate_move_plan())

    assert result["status"] == "success"
    assert result["action"] == "generate_move_plan"
    assert result["data"]["mode"] == "dry-run"

    plan = result["data"]["move_plan"]
    assert plan["dry_run"] is True
    assert plan["status"] == "pending_approval"
    assert plan["requires_approval"] is True
    assert len(plan["candidates"]) == 1
    assert plan["candidates"][0]["proposed_folder"].startswith("電費單/")
    assert plan["validation_report"] is not None
    assert plan["validation_report"]["approval_required"] is True


# ---------------------------------------------------------------------------
# 測試 7 + 8：MovePlan 建立 approval，payload 標記為 move_plan
# ---------------------------------------------------------------------------


def test_move_plan_creates_approval_with_move_plan_type(
    taipower_inbox, isolated_approvals
):
    output = mock_line_payload("產生搬移計畫")

    approvals = list(isolated_approvals._store.values())
    assert len(approvals) == 1
    payload = approvals[0].payload

    assert payload["plan_type"] == "move_plan"
    assert payload["dry_run"] is True
    assert payload["status"] == "pending_approval"
    assert "plan_id" in payload
    assert "candidates" in payload
    assert payload["validation_report"] is not None
    assert approvals[0].approval_id in output


# ---------------------------------------------------------------------------
# 測試 9–12：Mock LINE 輸出內容
# ---------------------------------------------------------------------------


def test_mock_line_move_plan_output(taipower_inbox, isolated_approvals):
    output = mock_line_payload("產生搬移計畫")

    # MovePlan 標題與 dry-run 標示
    assert "已產生搬移計畫" in output
    assert "dry-run" in output
    # 風險摘要
    assert "風險摘要" in output
    assert "低風險" in output and "封鎖" in output
    # 每筆內容
    assert "bill.pdf" in output
    assert "建議資料夾：電費單/" in output
    assert "建議目標路徑：電費單/" in output
    assert "信心度：" in output
    assert "風險：" in output
    # approval_id 與明確提示
    assert "approval_id：" in output
    assert "尚未實際搬移" in output
    # 不可出現「確認搬移」指令提示
    assert "確認搬移" not in output


# ---------------------------------------------------------------------------
# 測試 13：「整理資料夾」不會搬移檔案、不會建立資料夾
# ---------------------------------------------------------------------------


def test_move_planning_does_not_move_files(taipower_inbox, isolated_approvals, tmp_path):
    before = _snapshot(tmp_path)

    output = mock_line_payload("整理資料夾")

    assert "已產生搬移計畫" in output
    after = _snapshot(tmp_path)
    # 只允許多出 approval store 檔案，不允許出現任何新資料夾或被搬移的 PDF
    new_entries = set(after) - set(before)
    assert new_entries <= {"approvals.json"}, f"不應出現其他新檔案/資料夾：{new_entries}"
    assert (taipower_inbox / "bill.pdf").exists(), "PDF 不應被搬移"


# ---------------------------------------------------------------------------
# 測試 14 + 15：沒有真實 move executor、「確認搬移」不存在也不可觸發
# ---------------------------------------------------------------------------


def test_no_real_move_executor_exists():
    folder_module_dir = (
        Path(__file__).resolve().parent.parent / "app" / "folder_intelligence"
    )
    assert not (folder_module_dir / "executor.py").exists(), (
        "本階段不可有 move executor"
    )
    source = inspect.getsource(mock_line_module)
    assert "確認搬移" not in source, "Mock LINE 不可有「確認搬移」指令"


def test_confirm_move_command_does_not_trigger_anything(
    taipower_inbox, isolated_approvals
):
    mock_line_payload("產生搬移計畫")
    approval_id = list(isolated_approvals._store.keys())[0]

    output = mock_line_payload(f"確認搬移 {approval_id}")

    assert "已執行" not in output
    assert (taipower_inbox / "bill.pdf").exists()


# ---------------------------------------------------------------------------
# 測試 15b：「確認改名」不可執行 move plan approval（payload 防護）
# ---------------------------------------------------------------------------


def test_confirm_rename_rejects_move_plan_approval(taipower_inbox, isolated_approvals):
    mock_line_payload("產生搬移計畫")
    approval_id = list(isolated_approvals._store.keys())[0]
    isolated_approvals.approve(approval_id)

    output = mock_line_payload(f"確認改名 {approval_id}")

    assert "不是改名計畫" in output
    assert "已執行改名" not in output
    assert (taipower_inbox / "bill.pdf").exists(), "move plan 不可被當成 rename plan 執行"


# ---------------------------------------------------------------------------
# 測試 15c：「確認 {approval_id}」核准後顯示 move dry-run 報告，仍不搬移
# ---------------------------------------------------------------------------


def test_approve_move_plan_shows_dry_run_report(taipower_inbox, isolated_approvals):
    mock_line_payload("產生搬移計畫")
    approval_id = list(isolated_approvals._store.keys())[0]

    output = mock_line_payload(f"確認 {approval_id}")

    assert "搬移計畫已確認（dry-run）" in output
    assert "建議搬移至 電費單/" in output
    assert "本次沒有實際搬移任何檔案" in output
    assert (taipower_inbox / "bill.pdf").exists(), "核准後仍不可搬移檔案"
    assert isolated_approvals.get(approval_id).status == "approved"


# ---------------------------------------------------------------------------
# 測試 16：AST 驗證本次整合模組沒有真實搬移呼叫
# ---------------------------------------------------------------------------


def test_integration_modules_have_no_move_calls():
    import ast

    import app.router.ai_router as ai_router_module
    import app.workflows.executor as workflow_executor_module

    forbidden_imports = {"shutil"}

    for module in (mock_line_module, ai_router_module, workflow_executor_module):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports, (
                        f"{module.__name__} 不可 import {alias.name}"
                    )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("rename", "move", "replace"), (
                    f"{module.__name__} 不可呼叫 .{node.func.attr}()"
                )


# ---------------------------------------------------------------------------
# 測試 17：搬移目標使用 filename intelligence 的建議檔名（若有）
# ---------------------------------------------------------------------------


def test_move_plan_uses_proposed_filename_from_filename_intelligence(
    taipower_inbox, isolated_approvals
):
    from app.workers.pdf_worker import PDFWorker

    result = asyncio.run(PDFWorker().generate_move_plan())
    candidate = result["data"]["move_plan"]["candidates"][0]

    # 此 fixture PDF 可被 filename intelligence 產生建議檔名（台電電費單_...）
    proposed_path = candidate["proposed_path"]
    assert proposed_path.startswith("電費單/")
    assert "台電電費單" in proposed_path, (
        "move 目標應沿用 filename intelligence 的建議檔名"
    )
