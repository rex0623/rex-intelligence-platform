import asyncio
from pathlib import Path

from app.router.ai_router import AIRouter
from app.workflows.engine import WorkflowEngine
from app.workflows.executor import WorkflowExecutor
from app.approvals.manager import ApprovalManager


def test_execute_dry_run_report_can_be_generated():
    engine = WorkflowEngine()
    executor = WorkflowExecutor()
    plan = engine.create_workflow("pdf_bill", title="電費單處理流程")

    report = executor.execute_dry_run(plan)

    assert report["workflow_id"] == plan.workflow_id
    assert report["workflow_type"] == "pdf_bill"
    assert report["status"] == "dry_run_completed"
    assert isinstance(report["steps"], list)
    assert report["steps"][0]["name"] == "掃描 PDF"
    assert "dry-run completed" in report["steps"][0]["result"]
    assert report["note"] == "本次沒有修改任何 PDF"


def test_execute_dry_run_does_not_modify_files(tmp_path: Path):
    executor = WorkflowExecutor()
    plan = {
        "workflow_id": "test-wf",
        "workflow_type": "pdf_bill",
        "title": "test",
        "summary": "summary",
        "steps": [
            {"name": "掃描 PDF", "description": "scan", "requires_approval": False},
            {"name": "批次更名", "description": "rename", "requires_approval": False},
        ],
        "status": "waiting_approval",
        "dry_run": True,
    }

    file_path = tmp_path / "sample.txt"
    file_path.write_text("keep me", encoding="utf-8")
    before = sorted([p.name for p in tmp_path.iterdir()])

    report = executor.execute_dry_run(plan)

    after = sorted([p.name for p in tmp_path.iterdir()])
    assert before == after
    assert "dry-run completed" in report["steps"][0]["result"]
    assert report["steps"][1]["result"] == "dry-run blocked，需要正式 approval，Phase 9 不執行"


def test_confirmed_approval_generates_dry_run_report(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_file)
    engine = WorkflowEngine()
    plan = engine.create_workflow("pdf_bill", title="電費單處理流程")
    approval = manager.create_approval(plan.model_dump())

    monkeypatch.setattr("app.router.ai_router.approval_manager", manager)

    router = AIRouter()
    result = asyncio.run(router.route(message=f"確認 {approval.approval_id}"))
    worker_response = result.get("worker_response")

    assert result["status"] == "success"
    assert worker_response["status"] == "dry_run_completed"
    assert worker_response["workflow_id"] == approval.workflow_id
    assert worker_response["workflow_type"] == "pdf_bill"
    assert any(step["name"] == "掃描 PDF" for step in worker_response["steps"])


def test_missing_workflow_plan_returns_friendly_error(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "approvals.json"
    manager = ApprovalManager(store_path=store_file)
    plan = WorkflowEngine().create_workflow("pdf_bill", title="電費單處理流程")
    approval = manager.create_approval(plan.model_dump())
    manager._store[approval.approval_id].payload = None
    manager._save_store()

    monkeypatch.setattr("app.router.ai_router.approval_manager", manager)

    router = AIRouter()
    result = asyncio.run(router.route(message=f"確認 {approval.approval_id}"))
    worker_response = result.get("worker_response")

    assert result["status"] == "failed"
    assert "approval 尚未包含 workflow_plan" in worker_response
