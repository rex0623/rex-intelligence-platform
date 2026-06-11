"""Build MovePlan objects from document summaries (Phase 15A).

Planning only:
  - never checks the real filesystem
  - never creates folders
  - never moves files
"""

from app.folder_intelligence.schemas import MoveCandidate, MovePlan
from app.folder_intelligence.template import UNCLASSIFIED_FOLDER, build_taipower_folder


def _fields_from_document(doc: dict) -> dict:
    """Extract a name → value field mapping from a document dict.

    Accepts either:
      - "extracted_fields": {...} (direct dict), or
      - "document_object": {"fields": [{"name": ..., "value": ...}, ...]}
        (the pdf_summaries structure used by the rename pipeline).
    """
    extracted = doc.get("extracted_fields")
    if isinstance(extracted, dict) and extracted:
        return extracted

    doc_obj = doc.get("document_object") or {}
    result: dict = {}
    for f in doc_obj.get("fields", []):
        name = f.get("name", "")
        if name:
            result[name] = f.get("value", "")
    return result


def _filename_from_document(doc: dict) -> str:
    """Resolve the original filename from filename / file_name / path."""
    filename = doc.get("filename") or doc.get("file_name") or ""
    if filename:
        return filename
    path = str(doc.get("path", "") or "")
    if path:
        # 純字串處理，不碰 filesystem；不用 str.replace() 以符合本模組
        # 「不得出現 rename/move/replace 呼叫」的 AST 安全防護
        normalized = "/".join(path.split("\\"))
        return normalized.rstrip("/").rsplit("/", 1)[-1]
    return ""


def build_move_plan(documents: list[dict]) -> MovePlan:
    """Build a dry-run MovePlan from a list of document dicts.

    Each document may contain: path, filename / file_name, document_type,
    extracted_fields (or document_object.fields), proposed_filename,
    confidence.  An existing proposed_filename (from filename intelligence)
    takes priority over the original filename for the target path.
    """
    plan = MovePlan(total_files=len(documents))

    for doc in documents:
        original_path = str(doc.get("path", "") or "")
        original_filename = _filename_from_document(doc)

        doc_type_raw = doc.get("document_type", "unknown")
        doc_type = (
            doc_type_raw.value if hasattr(doc_type_raw, "value") else str(doc_type_raw)
        )

        fields = _fields_from_document(doc)
        target_filename = doc.get("proposed_filename") or original_filename

        warnings: list[str] = []
        errors: list[str] = []

        if doc_type == "taipower_bill":
            folder, confidence, warnings = build_taipower_folder(fields)
            reason = "依 business_id 與計費期間歸檔台電電費單"
        else:
            folder = UNCLASSIFIED_FOLDER
            confidence = 0.0
            reason = f"文件類型 {doc_type} 尚不支援自動歸檔"
            warnings = [reason]

        # 文件本身帶有信心度（如 filename intelligence 結果）時取較保守值
        doc_confidence = doc.get("confidence")
        if isinstance(doc_confidence, (int, float)):
            confidence = min(confidence, float(doc_confidence))

        if not original_path:
            errors.append("缺少原始路徑")

        proposed_path = folder + target_filename if target_filename else folder

        plan.candidates.append(MoveCandidate(
            original_path=original_path,
            original_filename=original_filename,
            proposed_folder=folder,
            proposed_path=proposed_path,
            document_type=doc_type,
            confidence=confidence,
            reason=reason,
            extracted_fields=fields,
            warnings=warnings,
            errors=errors,
            requires_approval=True,
        ))

    return plan
