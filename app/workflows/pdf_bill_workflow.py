"""Define the PDF bill processing workflow (dry-run)."""

from typing import List

from app.workflows.base import WorkflowPlan, WorkflowStep


def create_pdf_bill_workflow(title: str = "電費單處理流程", summary: str = "處理電費單的多步驟流程") -> WorkflowPlan:
    steps: List[WorkflowStep] = []

    steps.append(WorkflowStep(name="掃描 PDF", description="掃描 SAFE_PDF_ROOT 下的 PDF 檔案", worker="pdf_worker"))
    steps.append(WorkflowStep(name="讀取電號", description="從 PDF 中擷取電號", worker="pdf_worker"))
    steps.append(WorkflowStep(name="讀取計費期間", description="從 PDF 中擷取計費期間", worker="pdf_worker"))
    steps.append(WorkflowStep(name="對照案場名稱", description="比對案場名稱 mapping", worker="pdf_worker"))
    steps.append(WorkflowStep(name="建議新檔名", description="根據資訊建議新的檔名", worker="pdf_worker"))
    steps.append(WorkflowStep(name="等待使用者確認", description="等待使用者核准建議的檔名", requires_approval=True))
    steps.append(WorkflowStep(name="批次更名", description="批次更名 PDF 並備份", worker="pdf_worker"))
    steps.append(WorkflowStep(name="加入浮水印", description="在 PDF 加入浮水印", worker="pdf_worker"))
    steps.append(WorkflowStep(name="輸出結果", description="匯出處理報告與歸檔", worker="pdf_worker"))

    plan = WorkflowPlan(
        workflow_type="pdf_bill",
        title=title,
        summary=summary,
        steps=steps,
        status="waiting_approval",
        dry_run=True,
    )

    return plan
