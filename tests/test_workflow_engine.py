"""Tests for the Workflow Engine and pdf_bill workflow."""

from app.workflows.engine import WorkflowEngine


def test_create_pdf_bill_workflow():
    engine = WorkflowEngine()
    plan = engine.create_workflow("pdf_bill", title="Test PDF Bill")

    assert plan.workflow_type == "pdf_bill"
    assert plan.dry_run is True
    assert plan.status == "waiting_approval"
    assert len(plan.steps) == 9
    # check one step requires approval
    assert any(s.requires_approval for s in plan.steps)
