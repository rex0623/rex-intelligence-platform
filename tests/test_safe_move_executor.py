"""Phase 15D 測試：Safe Move Executor。

execute_move_plan() 是唯一可真實搬移檔案的入口：
- 只接受 approved 且帶 validation_report 的 MovePlan
- blocked_count > 0 時不執行
- high-risk 預設跳過，low / medium 才可搬移
- 所有真實搬移測試一律使用 pytest tmp_path
- Mock LINE 沒有任何指令會觸發真實搬移
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.folder_intelligence import execute_move_plan
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
    status: str = "approved",
    blocked_count: int | None = None,
) -> MovePlan:
    """建立帶有完整 MoveValidationReport 的 MovePlan。"""
    plan = MovePlan(total_files=len(candidates), status=status)
    plan.candidates = list(candidates)
    plan.validation_report = MoveValidationReport(
        total_files=len(candidates),
        low_count=sum(1 for r in risk_levels if r == "low"),
        medium_count=sum(1 for r in risk_levels if r == "medium"),
        high_count=sum(1 for r in risk_levels if r == "high"),
        blocked_count=(
            blocked_count
            if blocked_count is not None
            else sum(1 for r in risk_levels if r == "blocked")
        ),
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


# ---------------------------------------------------------------------------
# 測試 1–3：plan-level gates（不搬移、executed=False）
# ---------------------------------------------------------------------------


def test_executor_rejects_non_approved_plan(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"], status="pending_approval")

    result = execute_move_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert all(r.reason == "plan_not_approved" for r in result.results)
    assert Path(c.original_path).exists(), "未核准的 plan 不可搬移檔案"
    assert not Path(c.proposed_path).exists()


def test_executor_rejects_missing_validation_report(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = MovePlan(total_files=1, status="approved")
    plan.candidates = [c]
    # 刻意不設定 validation_report

    result = execute_move_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert all(r.reason == "missing_validation_report" for r in result.results)
    assert Path(c.original_path).exists()


def test_executor_rejects_blocked_count_in_report(tmp_path):
    good = _tmp_candidate(tmp_path, "good.pdf")
    bad = _tmp_candidate(tmp_path, "bad.pdf")
    plan = _make_plan([good, bad], ["low", "blocked"])

    result = execute_move_plan(plan)

    assert result.executed is False
    assert result.success_count == 0
    assert all(
        r.reason == "validation_has_blocked_candidates" for r in result.results
    )
    assert Path(good.original_path).exists(), "blocked plan 不可搬移任何檔案"
    assert Path(bad.original_path).exists()


# ---------------------------------------------------------------------------
# 測試 4 + 15：high-risk candidate 跳過、永不搬移
# ---------------------------------------------------------------------------


def test_executor_skips_high_risk_candidate(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["high"])

    result = execute_move_plan(plan)

    assert result.skipped_count == 1
    assert result.success_count == 0
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "high_risk_requires_manual_review"
    assert Path(c.original_path).exists(), "high-risk candidate 永不可搬移"
    assert not Path(c.proposed_path).exists()


# ---------------------------------------------------------------------------
# 測試 5：same_path 跳過
# ---------------------------------------------------------------------------


def test_executor_skips_same_path(tmp_path):
    src = tmp_path / "電費單" / "bill.pdf"
    src.parent.mkdir(parents=True)
    src.write_text("content")
    c = _candidate("bill.pdf", str(src), str(src))
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    assert result.skipped_count == 1
    assert result.results[0].status == "skipped"
    assert result.results[0].reason == "same_path"
    assert src.exists()


# ---------------------------------------------------------------------------
# 測試 6：source 不存在 → failed
# ---------------------------------------------------------------------------


def test_executor_fails_when_original_file_missing(tmp_path):
    c = _tmp_candidate(tmp_path, create_source=False)
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    assert result.failed_count == 1
    assert result.success_count == 0
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "original_file_not_found"
    assert not Path(c.proposed_path).exists()


# ---------------------------------------------------------------------------
# 測試 7：target 已存在 → failed，且不覆蓋
# ---------------------------------------------------------------------------


def test_executor_fails_when_target_already_exists(tmp_path):
    c = _tmp_candidate(tmp_path)
    target = Path(c.proposed_path)
    target.parent.mkdir(parents=True)
    target.write_text("existing-target")
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    assert result.failed_count == 1
    assert result.results[0].status == "failed"
    assert result.results[0].reason == "target_file_already_exists"
    assert Path(c.original_path).exists(), "collision 時不可動 source"
    assert target.read_text() == "existing-target", "collision 時不可覆蓋 target"


# ---------------------------------------------------------------------------
# 測試 8 + 9：low / medium candidate 成功搬移（tmp_path）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("risk", ["low", "medium"])
def test_executor_moves_low_and_medium_risk_candidate(tmp_path, risk):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], [risk])

    result = execute_move_plan(plan)

    assert result.executed is True
    assert result.dry_run is False
    assert result.success_count == 1
    assert result.results[0].status == "success"
    assert result.results[0].risk_level == risk
    assert Path(c.proposed_path).exists()
    assert Path(c.proposed_path).read_text() == "content-bill.pdf"


# ---------------------------------------------------------------------------
# 測試 10 + 11：成功搬移會建立目標資料夾、移除 source
# ---------------------------------------------------------------------------


def test_successful_move_creates_target_parent_folder(tmp_path):
    c = _tmp_candidate(tmp_path)
    assert not (tmp_path / "電費單").exists(), "前置條件：目標資料夾尚未存在"
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    assert result.success_count == 1
    assert Path(c.proposed_path).parent.is_dir(), "應自動建立目標資料夾"
    assert Path(c.proposed_path).exists()


def test_successful_move_removes_source_file(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    assert result.success_count == 1
    assert not Path(c.original_path).exists(), "搬移後 source 不應殘留"


# ---------------------------------------------------------------------------
# 測試 12：成功結果包含 rollback_from / rollback_to
# ---------------------------------------------------------------------------


def test_successful_move_returns_rollback_paths(tmp_path):
    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    r = result.results[0]
    assert r.status == "success"
    assert r.rollback_from == c.proposed_path, "rollback_from 應為新位置"
    assert r.rollback_to == c.original_path, "rollback_to 應為原位置"
    assert result.rollback_available is True


# ---------------------------------------------------------------------------
# 測試 13 + 16：混合候選的計數正確
# ---------------------------------------------------------------------------


def test_mixed_candidates_produce_correct_counts(tmp_path):
    c_low = _tmp_candidate(tmp_path, "low.pdf")
    c_medium = _tmp_candidate(tmp_path, "med.pdf")
    c_high = _tmp_candidate(tmp_path, "high.pdf")
    c_missing = _tmp_candidate(tmp_path, "ghost.pdf", create_source=False)
    plan = _make_plan(
        [c_low, c_medium, c_high, c_missing],
        ["low", "medium", "high", "low"],
    )

    result = execute_move_plan(plan)

    assert result.total == 4
    assert result.success_count == 2   # low + medium
    assert result.skipped_count == 1   # high
    assert result.failed_count == 1    # missing source
    assert result.blocked_count == 0
    assert result.executed is True
    assert result.rollback_available is True
    assert Path(c_low.proposed_path).exists()
    assert Path(c_medium.proposed_path).exists()
    assert Path(c_high.original_path).exists(), "high-risk 不可被搬移"


# ---------------------------------------------------------------------------
# 測試 14：candidate-level blocked 永不搬移
# ---------------------------------------------------------------------------


def test_blocked_candidate_is_never_moved(tmp_path):
    c = _tmp_candidate(tmp_path)
    # report 的 blocked_count 刻意設 0，以測試 candidate-level blocked 防線
    plan = _make_plan([c], ["blocked"], blocked_count=0)

    result = execute_move_plan(plan)

    assert result.blocked_count == 1
    assert result.success_count == 0
    assert result.results[0].status == "blocked"
    assert result.results[0].reason == "blocked_by_validation"
    assert Path(c.original_path).exists(), "blocked candidate 永不可搬移"
    assert not Path(c.proposed_path).exists()


# ---------------------------------------------------------------------------
# missing path 防線
# ---------------------------------------------------------------------------


def test_executor_fails_missing_original_path():
    c = _candidate("x.pdf", "", "電費單/x.pdf")
    plan = _make_plan([c], ["low"])

    result = execute_move_plan(plan)

    assert result.failed_count == 1
    assert result.results[0].reason == "missing_original_path"


def test_executor_fails_missing_proposed_path(tmp_path):
    c = _tmp_candidate(tmp_path)
    c.proposed_path = ""
    plan = _make_plan([c], ["low"])
    plan.validation_report.candidates[0].proposed_path = ""

    result = execute_move_plan(plan)

    assert result.failed_count == 1
    assert result.results[0].reason == "missing_proposed_path"
    assert Path(c.original_path).exists()


# ---------------------------------------------------------------------------
# 測試 17 + 18：Mock LINE 不可觸發真實搬移、「確認搬移」不存在
# ---------------------------------------------------------------------------


def test_mock_line_has_no_confirm_move_command_and_no_executor_wiring():
    import scripts.mock_line as mock_line_module

    source = inspect.getsource(mock_line_module)
    assert "確認搬移" not in source, "Mock LINE 不可有「確認搬移」指令"
    assert "execute_move_plan" not in source, (
        "Mock LINE 不可呼叫 move executor"
    )


def test_mock_line_move_keywords_do_not_trigger_actual_move(tmp_path, monkeypatch):
    """「整理資料夾」等指令僅產生計畫，不可真實搬移。"""
    from app.core.config import settings
    from scripts.mock_line import mock_line_payload

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
        mock_line_payload(keyword)
        assert pdf_path.exists(), f"「{keyword}」不可搬移原始 PDF"
        # 不可出現任何新資料夾（真實搬移會先建立目標資料夾）
        subdirs = [p for p in pdf_root.iterdir() if p.is_dir()]
        assert subdirs == [], f"「{keyword}」不可建立資料夾：{subdirs}"


# ---------------------------------------------------------------------------
# 測試 19：AST 驗證真實 move / rename 只存在於兩個 executor module
# ---------------------------------------------------------------------------


def test_real_move_calls_only_in_executor_modules():
    """app/ 與 scripts/ 下，.rename() / .move() 只允許出現在
    app/filename/executor.py 與 app/folder_intelligence/executor.py。"""
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
# 測試 20–22：既有模組仍可正常運作（完整回歸由整體 pytest 驗證）
# ---------------------------------------------------------------------------


def test_move_preflight_still_read_only(tmp_path):
    from app.folder_intelligence import preflight_move_plan

    c = _tmp_candidate(tmp_path)
    plan = _make_plan([c], ["low"])

    result = preflight_move_plan(plan)

    assert result.executed is False
    assert result.dry_run is True
    assert result.success_count == 0
    assert Path(c.original_path).exists(), "preflight 仍不可搬移檔案"
    assert not Path(c.proposed_path).exists()


def test_move_plan_workflow_modules_still_importable():
    from app.folder_intelligence import (
        build_move_plan,
        format_move_plan_for_cli,
        validate_move_plan,
    )

    assert callable(build_move_plan)
    assert callable(validate_move_plan)
    assert callable(format_move_plan_for_cli)


def test_rename_executor_still_importable_and_gated():
    from app.filename.executor import execute_rename_plan
    from app.filename.schemas import RenamePlan

    plan = RenamePlan(total_files=0, status="pending_approval")
    result = execute_rename_plan(plan)
    assert result.executed is False
