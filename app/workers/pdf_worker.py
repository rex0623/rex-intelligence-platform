"""PDF Worker for RIP."""

from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.document.classifier import classify_document_type
from app.document.extractor import extract_fields
from app.document.parser import parse_text
from app.document.schemas import Document
from app.schemas.messages import WorkerRequest
from app.workers.base import BaseWorker

logger = get_logger(__name__)


class PDFWorker(BaseWorker):
    """Worker for PDF processing."""

    def __init__(self):
        """Initialize PDF worker."""
        super().__init__(worker_id="pdf_worker", name="PDF Worker")
        from app.core.config import settings

        self.safe_pdf_root = Path(settings.SAFE_PDF_ROOT).expanduser().resolve()

    async def validate(self, request: WorkerRequest) -> bool:
        """
        Validate PDF worker request.

        Args:
            request: Worker request

        Returns:
            True if valid
        """
        if request.action not in [
            "extract_text",
            "extract_images",
            "extract_tables",
            "analyze_pdfs",
            "generate_rename_plan",
            "generate_move_plan",
        ]:
            return False

        return True

    async def process(self, request: WorkerRequest) -> dict[str, Any]:
        """
        Process PDF request.

        Args:
            request: Worker request

        Returns:
            Processing result
        """
        action = request.action

        logger.info(f"PDF Worker processing: {action}")

        if action == "analyze_pdfs":
            return await self.analyze_pdfs()

        if action == "generate_rename_plan":
            return await self.generate_rename_plan()

        if action == "generate_move_plan":
            return await self.generate_move_plan()

        if action == "extract_text":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "text": "這是從 PDF 提取的模擬文本。\n"
                    "PDF 文件已成功處理。\n"
                    "此為 Phase 1 的演示數據。",
                    "pages": 5,
                    "file_name": request.payload.get("file_name", "document.pdf"),
                },
            }

        elif action == "extract_images":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "images": [
                        {"id": 1, "page": 1, "size": "100KB"},
                        {"id": 2, "page": 3, "size": "150KB"},
                    ],
                    "file_name": request.payload.get("file_name", "document.pdf"),
                },
            }

        elif action == "extract_tables":
            return {
                "status": "success",
                "action": action,
                "data": {
                    "tables": [
                        {
                            "id": 1,
                            "page": 2,
                            "rows": 10,
                            "columns": 5,
                            "preview": "Table 1 data preview...",
                        }
                    ],
                    "file_name": request.payload.get("file_name", "document.pdf"),
                },
            }

        return {
            "status": "error",
            "error": f"Unknown action: {action}",
        }

    def classify_pdf(self, text: str) -> dict[str, object]:
        """Classify a PDF from its text content."""
        result = classify_document_type(text)
        return {"type": result["document_type"].value, "confidence": result["confidence"]}

    async def analyze_pdfs(self) -> dict[str, Any]:
        return self._analyze_pdfs_sync()

    async def generate_rename_plan(self) -> dict[str, Any]:
        from app.filename.planner import build_rename_plan
        from app.filename.validator import validate_rename_plan

        analysis = self._analyze_pdfs_sync()
        if analysis.get("status") == "error":
            return analysis
        summaries = analysis.get("data", {}).get("pdf_summaries", [])
        plan = build_rename_plan(summaries)
        plan.validation_report = validate_rename_plan(plan)
        return {
            "status": "success",
            "action": "generate_rename_plan",
            "data": {
                "mode": "dry-run",
                "message": "dry-run，不會實際更名",
                "rename_plan": plan.model_dump(),
            },
        }

    async def generate_move_plan(self) -> dict[str, Any]:
        """Generate a dry-run MovePlan (Phase 15B).

        Planning only: never creates folders, never moves files.
        """
        from app.filename.planner import build_rename_plan
        from app.folder_intelligence.planner import build_move_plan
        from app.folder_intelligence.validator import validate_move_plan

        analysis = self._analyze_pdfs_sync()
        if analysis.get("status") == "error":
            return analysis
        summaries = analysis.get("data", {}).get("pdf_summaries", [])

        # 沿用 filename intelligence 的建議檔名（若有），讓搬移目標使用
        # 正規化後的檔名；planner 僅產生字串，不更名任何檔案。
        rename_plan = build_rename_plan(summaries)
        proposed_by_file = {
            c.original_filename: c.proposed_filename
            for c in rename_plan.candidates
            if c.proposed_filename
        }

        documents = []
        for summary in summaries:
            file_name = summary.get("file_name", "")
            doc_obj = summary.get("document_object") or {}
            doc_type = doc_obj.get(
                "document_type",
                summary.get("classification", {}).get("type", "unknown"),
            )
            documents.append({
                "path": str(self.safe_pdf_root / file_name) if file_name else "",
                "filename": file_name,
                "document_type": doc_type,
                "document_object": doc_obj,
                "proposed_filename": proposed_by_file.get(file_name),
            })

        plan = build_move_plan(documents)
        plan.validation_report = validate_move_plan(plan)
        return {
            "status": "success",
            "action": "generate_move_plan",
            "data": {
                "mode": "dry-run",
                "message": "dry-run，不會實際搬移",
                "move_plan": plan.model_dump(),
            },
        }

    def _analyze_pdfs_sync(self) -> dict[str, Any]:
        target = self.safe_pdf_root
        try:
            home = Path.home().resolve()
            if target == Path("/") or target == home or str(target).rstrip(":\\") in ["C:"]:
                return {
                    "status": "error",
                    "action": "analyze_pdfs",
                    "error": "目錄不允許掃描。",
                }
        except Exception:
            pass

        if not target.exists():
            return {
                "status": "error",
                "action": "analyze_pdfs",
                "error": f"PDF 目錄不存在：{target}",
            }

        pdf_files = [path for path in target.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"]
        summaries = []
        document_objects = []
        readable_count = 0
        classification_counts: dict[str, int] = {}

        try:
            import fitz
        except ImportError:
            return {
                "status": "error",
                "action": "analyze_pdfs",
                "error": "PyMuPDF 未安裝，無法分析 PDF。",
            }

        for path in pdf_files:
            file_size = path.stat().st_size
            file_info = {
                "file_name": path.name,
                "file_size": file_size,
                "page_count": 0,
                "creator": "",
                "producer": "",
                "encrypted": False,
                "readable": False,
                "text_length": 0,
                "first_200_chars": "",
                "classification": {"type": "unknown", "confidence": 0.0},
                "document_object": None,
            }

            try:
                doc = fitz.open(path)
                file_info["encrypted"] = doc.is_encrypted
                file_info["page_count"] = doc.page_count
                metadata = doc.metadata or {}
                file_info["creator"] = metadata.get("creator", "") or ""
                file_info["producer"] = metadata.get("producer", "") or ""

                if not doc.is_encrypted and doc.page_count > 0:
                    raw_text = doc.load_page(0).get_text()
                    normalized_text = parse_text(raw_text)
                    file_info["readable"] = True
                    file_info["text_length"] = len(normalized_text)
                    file_info["first_200_chars"] = normalized_text[:200]

                    classification = classify_document_type(normalized_text)
                    document = Document(
                        document_type=classification["document_type"],
                        confidence=float(classification["confidence"]),
                        fields=extract_fields(normalized_text),
                        text=normalized_text,
                        source_file=path.name,
                    )
                    file_info["classification"] = {"type": classification["document_type"].value, "confidence": classification["confidence"]}
                    file_info["document_object"] = document.model_dump()
                    document_objects.append(document.model_dump())
                    readable_count += 1
                else:
                    file_info["classification"] = {"type": "unknown", "confidence": 0.0}

                doc.close()
            except Exception:
                file_info["readable"] = False
                file_info["classification"] = {"type": "unknown", "confidence": 0.0}

            classification_counts[file_info["classification"]["type"]] = (
                classification_counts.get(file_info["classification"]["type"], 0) + 1
            )
            summaries.append(file_info)

        return {
            "status": "success",
            "action": "analyze_pdfs",
            "data": {
                "mode": "dry-run",
                "message": "dry-run，不會修改任何 PDF",
                "total_pdfs": len(pdf_files),
                "readable_pdfs": readable_count,
                "classification_counts": classification_counts,
                "pdf_summaries": summaries,
                "document_objects": document_objects,
            },
        }
