"""Build RenamePlan objects from PDF analysis summaries."""

from app.document.schemas import DocumentType
from app.filename.schemas import RenameCandidate, RenamePlan
from app.filename.template import build_taipower_filename


def _fields_dict(doc: dict) -> dict[str, str]:
    """Convert a document_object fields list to a name → value mapping."""
    result: dict[str, str] = {}
    for f in doc.get("fields", []):
        name = f.get("name", "")
        value = f.get("value", "")
        if name:
            result[name] = str(value) if not isinstance(value, str) else value
    return result


def _resolve_collision(proposed: str, seen: set) -> str:
    """Append _2, _3, … before the extension until unique within *seen*."""
    if proposed not in seen:
        return proposed
    stem, dot, ext = proposed.rpartition(".")
    if not stem:
        stem, ext, dot = proposed, "", ""
    counter = 2
    while True:
        candidate = f"{stem}_{counter}{dot}{ext}"
        if candidate not in seen:
            return candidate
        counter += 1


def build_rename_plan(pdf_summaries: list) -> RenamePlan:
    """Build a RenamePlan from a list of pdf_summary dicts (from PDFWorker)."""
    plan = RenamePlan(total_files=len(pdf_summaries))
    seen_proposed: set[str] = set()

    for summary in pdf_summaries:
        filename = summary.get("file_name", "unknown.pdf")
        doc_obj = summary.get("document_object") or {}

        doc_type_raw = doc_obj.get("document_type", "unknown")
        doc_type = (
            doc_type_raw.value if hasattr(doc_type_raw, "value") else str(doc_type_raw)
        )

        if doc_type == DocumentType.taipower_bill.value:
            fields = _fields_dict(doc_obj)
            proposed, confidence, cand_warnings = build_taipower_filename(
                fields, filename
            )
            if proposed:
                proposed = _resolve_collision(proposed, seen_proposed)
                seen_proposed.add(proposed)
        else:
            proposed = None
            confidence = 0.0
            cand_warnings = [f"文件類型 {doc_type} 尚不支援自動改名"]

        candidate = RenameCandidate(
            original_filename=filename,
            proposed_filename=proposed,
            confidence=confidence,
            document_type=doc_type,
            warnings=cand_warnings,
        )
        plan.candidates.append(candidate)
        if proposed:
            plan.renamed_count += 1

    return plan
