"""Document intelligence schemas."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    taipower_bill = "taipower_bill"
    invoice = "invoice"
    contract = "contract"
    unknown = "unknown"


class DocumentField(BaseModel):
    name: str
    value: str
    confidence: float = Field(default=0.0)


class Document(BaseModel):
    document_type: DocumentType
    confidence: float = Field(default=0.0)
    fields: List[DocumentField] = Field(default_factory=list)
    text: Optional[str] = ""
    source_file: Optional[str] = None
