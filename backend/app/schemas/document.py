from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    document_id: int
    original_filename: str
    file_type: str
    file_size: int
    status: str
    uploaded_at: datetime | None
    message: str


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    id: int
    invoice_id: int | None
    original_filename: str
    mime_type: str | None
    file_type: str | None
    processing_status: str
    extraction_notes: str | None
    uploaded_at: datetime | None


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int
    page: int
    page_size: int
    pages: int


class DocumentDetailResponse(BaseModel):
    document_id: int
    id: int
    invoice_id: int | None
    original_filename: str
    mime_type: str | None
    file_type: str | None
    processing_status: str
    extraction_notes: str | None
    uploaded_at: datetime | None
    file_size: int | None
    extracted_data: dict[str, Any] | None


class DocumentRejectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
