
import logging
import mimetypes
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_admin
from app.models import (
    AdminUser,
    AuditLog,
    Invoice,
    InvoiceItem,
    InvoiceDocument
)
from app.schemas.invoice import (
    InvoiceReviewItem,
    InvoiceReviewRequest,
    InvoiceReviewResponse,
    InvoiceValidationRequest,
)
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentRejectionRequest,
    DocumentUploadResponse,
)
from app.services.invoice_validator import (
    parse_invoice_amount,
    parse_invoice_date,
    validate_invoice,
)
from app.schemas.uae_invoice import CompleteInvoiceValidationResponse
from app.services.file_detector import (
    detect_file_type,
    extract_uploaded_file,
    validate_file_signature,
)
from app.agents.document_agent import document_agent


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/documents",
    tags=["Document Intelligence"],
    dependencies=[Depends(get_current_admin)]
)


MAX_FILE_SIZE = settings.max_upload_size_mb * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".csv"}


def save_uploaded_file(
    original_filename: str,
    file_bytes: bytes
) -> tuple[Path, str]:
    """Save files using a generated name in private storage."""

    extension = Path(original_filename).suffix.lower()

    storage_directory = Path(
        settings.invoice_storage_dir
    ).resolve()

    storage_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    stored_filename = f"{uuid4().hex}{extension}"

    file_path = storage_directory / stored_filename

    file_path.write_bytes(file_bytes)

    return file_path, str(file_path)


def create_audit_log(
    db: Session,
    admin_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    details: dict
):
    """Create an audit record with an explicit timestamp."""

    audit = AuditLog(
        admin_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        created_at=datetime.now(timezone.utc)
    )

    db.add(audit)


def document_to_response(document: InvoiceDocument) -> dict:
    """Convert document metadata to an API response."""

    extracted_data = document.extracted_data or {}
    return {
        "id": document.id,
        "document_id": document.id,
        "invoice_id": document.invoice_id,
        "original_filename": document.original_filename,
        "mime_type": document.mime_type,
        "file_type": extracted_data.get(
            "file_type",
            Path(document.original_filename).suffix.lower().lstrip("."),
        ),
        "processing_status": document.processing_status,
        "extraction_notes": document.extraction_notes,
        "extracted_data": extracted_data,
        "uploaded_at": (
            document.uploaded_at.isoformat()
            if document.uploaded_at
            else None
        )
    }


def _document_list_item(document: InvoiceDocument) -> dict:
    data = document.extracted_data or {}
    return {
        "id": document.id,
        "document_id": document.id,
        "invoice_id": document.invoice_id,
        "original_filename": document.original_filename,
        "mime_type": document.mime_type,
        "file_type": data.get(
            "file_type",
            Path(document.original_filename).suffix.lower().lstrip("."),
        ),
        "processing_status": document.processing_status,
        "extraction_notes": document.extraction_notes,
        "uploaded_at": document.uploaded_at,
    }


def _document_detail(document: InvoiceDocument) -> dict:
    result = document_to_response(document)
    result["file_size"] = (document.extracted_data or {}).get("file_size")
    return result


def _validation_fingerprint(values: dict) -> str:
    payload = json.dumps(
        values,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_upload_mime(content_type: str | None, extension: str) -> None:
    if not content_type or content_type == "application/octet-stream":
        return
    expected = {
        ".pdf": {"application/pdf"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        ".xlsx": {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        ".xls": {
            "application/vnd.ms-excel",
            "application/x-ole-storage",
        },
        ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    }
    if content_type.split(";", 1)[0].strip().lower() not in expected[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file content type does not match its extension.",
        )


def invoice_fields_were_corrected(
    original_fields: dict,
    reviewed: InvoiceReviewRequest
) -> bool:
    """Check whether the administrator changed extracted values."""

    values = {
        "invoice_number": reviewed.invoice_number,
        "customer_name": reviewed.customer_name,
        "customer_email": reviewed.customer_email,
        "amount_aed": reviewed.amount_aed,
        "issue_date": reviewed.issue_date,
        "due_date": reviewed.due_date
    }

    for field, new_value in values.items():

        old_value = original_fields.get(field)

        if field == "amount_aed":
            old_amount = parse_invoice_amount(old_value)

            if old_amount != new_value:
                return True

        elif field in ("issue_date", "due_date"):
            old_date = parse_invoice_date(old_value)

            if old_date != new_value:
                return True

        else:
            old_text = (
                str(old_value).strip().casefold()
                if old_value is not None
                else None
            )

            new_text = (
                str(new_value).strip().casefold()
                if new_value is not None
                else None
            )

            if old_text != new_text:
                return True

    return False


def _source_invoice(extracted_data: dict, invoice_index: int = 0) -> dict:
    structured = extracted_data.get("structured_invoice")
    if invoice_index == 0 and isinstance(structured, dict):
        return structured
    result = extracted_data.get("structured_extraction")
    if isinstance(result, dict):
        invoices = result.get("invoices")
        if (
            isinstance(invoices, list)
            and invoice_index < len(invoices)
            and isinstance(invoices[invoice_index], dict)
        ):
            return invoices[invoice_index]
    return {}


def _invoice_data_for_validation(
    extracted_data: dict,
    submitted: InvoiceValidationRequest,
) -> dict:
    invoice_index = submitted.invoice_index
    structured = extracted_data.get("structured_extraction")
    invoice_records = (
        structured.get("invoices") if isinstance(structured, dict) else None
    )
    invoice_count = (
        len(invoice_records)
        if isinstance(invoice_records, list) and invoice_records
        else 1 if isinstance(extracted_data.get("structured_invoice"), dict) else 0
    )
    if invoice_index >= invoice_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected invoice does not exist in this document.",
        )
    approved_indices = extracted_data.get("approved_invoice_indices")
    if isinstance(approved_indices, list) and invoice_index in approved_indices:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice from the document has already been approved.",
        )
    source = _source_invoice(extracted_data, invoice_index)
    extracted_fields = extracted_data.get("fields")
    invoice_reviews = extracted_data.get("invoice_reviews")
    corrected_fields = (
        invoice_reviews.get(str(invoice_index))
        if isinstance(invoice_reviews, dict)
        else None
    )
    if invoice_index == 0:
        corrected_fields = corrected_fields or extracted_data.get("corrected_values")
        reviewed_fields = extracted_data.get("reviewed_values")
        if isinstance(reviewed_fields, dict):
            extracted_fields = reviewed_fields
    if isinstance(corrected_fields, dict):
        extracted_fields = corrected_fields
    elif invoice_index != 0:
        extracted_fields = {}
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}
    values = {
        key: source.get(key)
        for key in (
            "invoice_number", "supplier_name", "supplier_trn",
            "supplier_address", "supplier_emirate", "customer_name",
            "customer_trn", "customer_email", "customer_address",
            "customer_emirate", "place_of_supply", "currency",
            "issue_date", "supply_date", "due_date", "items",
            "subtotal_aed", "discount_aed", "vat_amount_aed",
            "total_amount_aed",
        )
    }
    values.update({
        key: extracted_fields.get(key)
        for key in (
            "invoice_number", "supplier_name", "supplier_trn",
            "supplier_address", "supplier_emirate", "customer_name",
            "customer_trn", "customer_email", "customer_address",
            "customer_emirate", "place_of_supply", "currency",
            "issue_date", "supply_date", "due_date", "subtotal_aed",
            "discount_aed", "vat_amount_aed", "total_amount_aed",
        )
        if key in extracted_fields
    })
    values["amount_aed"] = extracted_fields.get(
        "amount_aed", values.get("total_amount_aed")
    )
    values["items"] = values.get("items") or []

    supplied = submitted.model_dump(mode="json", exclude_unset=True)
    if "items" in submitted.model_fields_set:
        supplied["items"] = [
            item.model_dump(mode="json")
            if isinstance(item, InvoiceReviewItem)
            else item
            for item in submitted.items
        ]
    values.update(supplied)
    values["invoice_index"] = invoice_index
    if (
        "amount_aed" in submitted.model_fields_set
        and "total_amount_aed" not in submitted.model_fields_set
    ):
        values["total_amount_aed"] = values.get("amount_aed")
    if values.get("total_amount_aed") is None:
        values["total_amount_aed"] = values.get("amount_aed")
    if values.get("amount_aed") is None:
        values["amount_aed"] = values.get("total_amount_aed")
    return values


def _document_content_hash(document: InvoiceDocument | None) -> str | None:
    if document is None:
        return None
    metadata = document.extracted_data or {}
    content_hash = metadata.get("content_sha256")
    if isinstance(content_hash, str) and content_hash:
        return content_hash
    path = Path(document.storage_path)
    if not path.is_file():
        logger.info(
            "Stored document %s is unavailable for duplicate-upload detection.",
            document.id,
        )
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        logger.warning(
            "Unable to hash stored document %s for duplicate-upload detection.",
            document.id,
        )
        return None


def _duplicate_invoice_check(
    db: Session,
    values: dict,
    document: InvoiceDocument | None = None,
) -> dict:
    current_hash = _document_content_hash(document)
    if current_hash:
        documents = db.scalars(select(InvoiceDocument)).all()
        duplicate_uploads = [
            existing_document
            for existing_document in documents
            if existing_document.id != getattr(document, "id", None)
            and existing_document.processing_status != "rejected"
            and (existing_document.extracted_data or {}).get("review_status")
            != "rejected"
            and _document_content_hash(existing_document) == current_hash
        ]
        if duplicate_uploads:
            return {
                "status": "duplicate_upload",
                "message": (
                    "This exact document has already been uploaded. Resolve "
                    "the matching uploads and validate again before approval."
                ),
                "matches": [
                    {
                        "document_id": existing_document.id,
                        "filename": existing_document.original_filename,
                        "processing_status": existing_document.processing_status,
                    }
                    for existing_document in duplicate_uploads
                ],
            }

    invoice_number = str(values.get("invoice_number") or "").strip()
    if not invoice_number:
        return {"status": "not_checked", "message": "Invoice number is missing."}

    matches = db.scalars(
        select(Invoice).where(Invoice.invoice_number == invoice_number)
    ).all()
    current_invoice_id = document.invoice_id if document is not None else None
    matches = [
        existing
        for existing in matches
        if existing.id != current_invoice_id
    ]

    supplier_trn = str(values.get("supplier_trn") or "").strip()
    supplier_name = str(values.get("supplier_name") or "").strip().casefold()
    supplier_trn = supplier_trn.replace(" ", "").replace("-", "")
    invoice_matches = []
    ignored_demo_matches = []
    for existing in matches:
        record = {
            "invoice_id": existing.id,
            "invoice_number": existing.invoice_number,
            "supplier_name": existing.supplier_name,
            "supplier_trn": existing.supplier_trn,
            "source_type": getattr(existing, "source_type", None),
            "source_filename": getattr(existing, "source_filename", None),
        }
        if str(getattr(existing, "source_type", "") or "").casefold() == "demo":
            ignored_demo_matches.append(record)
            continue

        existing_trn = str(existing.supplier_trn or "").strip()
        existing_trn = existing_trn.replace(" ", "").replace("-", "")
        existing_name = str(existing.supplier_name or "").strip().casefold()
        same_supplier = (
            supplier_trn == existing_trn
            if supplier_trn and existing_trn
            else bool(supplier_name and existing_name and supplier_name == existing_name)
        )
        invoice_matches.append({
            **record,
            "classification": (
                "same_invoice" if same_supplier else "conflicting_number"
            ),
        })

    if invoice_matches:
        same_invoice = next(
            (
                match for match in invoice_matches
                if match["classification"] == "same_invoice"
            ),
            None,
        )
        if same_invoice:
            return {
                "status": "same_invoice",
                "message": "This invoice number is already registered for the same supplier.",
                "matches": invoice_matches,
            }
        return {
            "status": "conflicting_number",
            "message": (
                "This invoice number is registered to a different or "
                "unconfirmed supplier. Confirm the supplier or use the "
                "correct invoice number before approval."
            ),
            "matches": invoice_matches,
        }

    if ignored_demo_matches:
        return {
            "status": "clear",
            "message": (
                "No genuine duplicate found; matching synthetic demo invoices "
                "are ignored."
            ),
            "ignored_demo_matches": ignored_demo_matches,
        }
    return {"status": "clear", "message": "No matching invoice number found."}


def _record_document_validation(
    db: Session,
    document: InvoiceDocument,
    admin: AdminUser,
    values: dict,
    validation: dict,
    action: str = "invoice_document_validated",
) -> None:
    extracted_data = dict(document.extracted_data or {})
    invoice_index = int(values.get("invoice_index", 0))
    original_invoice = _source_invoice(extracted_data, invoice_index)
    fields = extracted_data.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    original_fields = {**original_invoice, **fields}
    if "amount_aed" not in original_fields:
        original_fields["amount_aed"] = original_fields.get("total_amount_aed")
    corrected_fields = (
        "invoice_number", "supplier_name", "supplier_address",
        "supplier_emirate", "supplier_trn", "customer_name",
        "customer_address", "customer_emirate", "customer_trn",
        "customer_email", "place_of_supply", "currency", "issue_date",
        "supply_date", "due_date", "amount_aed", "subtotal_aed",
        "discount_aed", "vat_amount_aed", "total_amount_aed", "items",
    )
    changed = [
        key for key in corrected_fields
        if key in values
        and str(values.get(key)) != str(original_fields.get(key))
    ]
    stored_history = extracted_data.get("revision_history")
    history = list(stored_history) if isinstance(stored_history, list) else []
    if changed:
        history.append({
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "corrected_fields": changed,
            "changes": {
                key: {
                    "extracted": original_fields.get(key),
                    "reviewed": values.get(key),
                }
                for key in changed
            },
        })
    extracted_data["revision_history"] = history[-50:]
    invoice_validations = extracted_data.get("invoice_validations")
    if not isinstance(invoice_validations, dict):
        invoice_validations = {}
    invoice_validations[str(invoice_index)] = {
        "result": validation,
        "input_fingerprint": _validation_fingerprint(values),
        "reviewed_values": {
            key: values.get(key) for key in corrected_fields if key in values
        },
    }
    invoice_reviews = extracted_data.get("invoice_reviews")
    if not isinstance(invoice_reviews, dict):
        invoice_reviews = {}
    prior_review = invoice_reviews.get(str(invoice_index))
    invoice_reviews[str(invoice_index)] = {
        **(prior_review if isinstance(prior_review, dict) else {}),
        **{
            key: values.get(key)
            for key in corrected_fields
            if key in values
        },
    }
    extracted_data["invoice_reviews"] = invoice_reviews
    extracted_data["invoice_validations"] = invoice_validations
    extracted_data["validation"] = validation
    extracted_data["validation_input_fingerprint"] = _validation_fingerprint(values)
    if invoice_index == 0:
        extracted_data["reviewed_values"] = {
            key: values.get(key) for key in corrected_fields if key in values
        }
    document.extracted_data = extracted_data
    create_audit_log(
        db=db,
        admin_id=admin.id,
        action=action,
        entity_type="invoice_document",
        entity_id=document.id,
        details={
            "is_valid": validation["is_valid"],
            "error_count": len(validation["errors"]),
            "warning_count": len(validation["warnings"]),
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
    )
    if changed:
        create_audit_log(
            db=db,
            admin_id=admin.id,
            action="invoice_administrator_corrections",
            entity_type="invoice_document",
            entity_id=document.id,
            details={"corrected_fields": changed},
        )


# ---------------------------------------------------------
# 1. Upload and extract supported invoice documents
# ---------------------------------------------------------

@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentUploadResponse,
    summary="Upload a private invoice document",
    description=(
        "Validates and stores a supported document privately. Extraction and "
        "AI processing are started separately by the authenticated administrator."
    ),
)
def upload_invoice_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    """Store an invoice source privately without processing or approving it."""
    raw_filename = (file.filename or "invoice").replace("\\", "/").split("/")[-1]
    original_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_filename)
    original_filename = original_filename.strip(" .")[-255:] or "invoice"

    try:
        extension = detect_file_type(original_filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    _validate_upload_mime(file.content_type, extension)

    file_bytes = file.file.read(MAX_FILE_SIZE + 1)
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Maximum upload size is {settings.max_upload_size_mb} MB.",
        )

    try:
        validate_file_signature(file_bytes, extension)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        _, storage_path = save_uploaded_file(original_filename, file_bytes)
    except OSError:
        logger.exception("Unable to save uploaded invoice document.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to store the uploaded document.",
        )

    mime_type = file.content_type or mimetypes.guess_type(original_filename)[0]
    uploaded_at = datetime.now(timezone.utc)
    extracted_data = {
        "file_type": extension[1:],
        "file_size": len(file_bytes),
        "content_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "uploaded_by_admin_id": current_admin.id,
        "uploaded_at": uploaded_at.isoformat(),
        "warnings": [],
    }
    document = InvoiceDocument(
        invoice_id=None,
        original_filename=original_filename,
        storage_path=storage_path,
        mime_type=mime_type,
        processing_status="uploaded",
        extraction_notes=None,
        extracted_data=extracted_data,
        uploaded_at=uploaded_at,
    )
    try:
        db.add(document)
        db.flush()
        create_audit_log(
            db=db,
            admin_id=current_admin.id,
            action="invoice_document_uploaded",
            entity_type="invoice_document",
            entity_id=document.id,
            details={
                "filename": original_filename,
                "file_type": extension[1:],
                "file_size": len(file_bytes),
            },
        )
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        try:
            Path(storage_path).unlink(missing_ok=True)
        except OSError:
            logger.exception("Unable to remove uncommitted uploaded file.")
        logger.exception("Unable to save extracted document metadata.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the extracted document.",
        )

    return {
        "document_id": document.id,
        "original_filename": original_filename,
        "file_type": extension[1:],
        "file_size": len(file_bytes),
        "status": "uploaded",
        "uploaded_at": uploaded_at,
        "message": "Document uploaded privately. Start processing when ready.",
    }


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List uploaded documents",
)
def list_documents(
    status_filter: str | None = Query(default=None, alias="status"),
    file_type: str | None = Query(default=None, max_length=10),
    search: str | None = Query(default=None, max_length=255),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated upload metadata without private storage locations."""
    statement = select(InvoiceDocument)
    if status_filter:
        statement = statement.where(
            InvoiceDocument.processing_status == status_filter
        )
    if file_type:
        extension = file_type.lower().lstrip(".")
        statement = statement.where(
            InvoiceDocument.original_filename.ilike(f"%.{extension}")
        )
    if search:
        statement = statement.where(
            InvoiceDocument.original_filename.ilike(f"%{search.strip()}%")
        )
    if date_from:
        statement = statement.where(
            func.date(InvoiceDocument.uploaded_at) >= date_from
        )
    if date_to:
        statement = statement.where(
            func.date(InvoiceDocument.uploaded_at) <= date_to
        )
    total = db.scalar(
        select(func.count()).select_from(statement.subquery())
    ) or 0
    documents = db.scalars(
        statement.order_by(InvoiceDocument.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "documents": [_document_list_item(document) for document in documents],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


# ---------------------------------------------------------
# 2. List documents waiting for administrator review
# ---------------------------------------------------------

@router.get("/pending")
def get_pending_documents(
    db: Session = Depends(get_db)
):
    """List successfully extracted documents not yet approved."""

    statement = (
        select(InvoiceDocument)
        .where(
            InvoiceDocument.processing_status.in_(
                ("uploaded", "pending_review", "processing_failed")
            )
        )
        .order_by(InvoiceDocument.id.desc())
    )

    documents = []
    for document in db.scalars(statement).all():
        data = document.extracted_data or {}
        structured = data.get("structured_extraction")
        extracted_invoices = (
            structured.get("invoices")
            if isinstance(structured, dict)
            else None
        )
        invoice_count = (
            len(extracted_invoices)
            if isinstance(extracted_invoices, list) and extracted_invoices
            else 1
        )
        approved = data.get("approved_invoice_indices")
        approved = approved if isinstance(approved, list) else []
        if (
            data.get("review_status") != "rejected"
            and len(set(approved)) < invoice_count
        ):
            documents.append(document)

    return {
        "count": len(documents),
        "documents": [
            document_to_response(document)
            for document in documents
        ]
    }


@router.post(
    "/{document_id}/validate",
    response_model=CompleteInvoiceValidationResponse,
)
def validate_document_invoice(
    document_id: int,
    review: InvoiceValidationRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Recalculate and persist validation for administrator-edited values."""
    document = db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.processing_status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed, unapproved documents can be validated.",
        )
    if (document.extracted_data or {}).get("review_status") == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A rejected document cannot be validated.",
        )

    values = _invoice_data_for_validation(document.extracted_data or {}, review)
    duplicate = _duplicate_invoice_check(db, values, document)
    values["duplicate"] = duplicate
    result = validate_invoice(values)
    try:
        _record_document_validation(
            db, document, current_admin, values, result
        )
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        logger.exception("Document validation could not be saved for %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save invoice validation results.",
        )
    return result


@router.post("/{document_id}/reject")
def reject_document_invoice(
    document_id: int,
    request: DocumentRejectionRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Reject an extracted document while retaining its private source and audit trail."""
    document = db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.invoice_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An approved invoice document cannot be rejected.",
        )
    data = dict(document.extracted_data or {})
    if document.processing_status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only documents pending review can be rejected.",
        )
    if data.get("review_status") == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been rejected.",
        )
    data["review_status"] = "rejected"
    data["rejection"] = {
        "reason": request.reason.strip(),
        "admin_id": current_admin.id,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }
    document.extracted_data = data
    document.processing_status = "rejected"
    document.extraction_notes = request.reason.strip()
    try:
        create_audit_log(
            db=db,
            admin_id=current_admin.id,
            action="invoice_document_rejected",
            entity_type="invoice_document",
            entity_id=document.id,
            details={
                "filename": document.original_filename,
                "reason": request.reason.strip(),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Document rejection could not be saved for %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to reject the invoice document.",
        )
    return {
        "message": "Document rejected and retained for audit.",
        "document_id": document.id,
        "status": "rejected",
    }


# ---------------------------------------------------------
# 3. Retrieve a document extraction result
# ---------------------------------------------------------

@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document processing and review details",
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve document metadata and its extracted fields."""

    document = db.get(
        InvoiceDocument,
        document_id
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )

    return _document_detail(document)


@router.put(
    "/{document_id}/corrections",
    response_model=DocumentDetailResponse,
    summary="Correct extracted invoice information",
)
def correct_document_invoice(
    document_id: int,
    corrections: InvoiceValidationRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Preserve extraction, store administrator corrections and revalidate."""
    document = db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.processing_status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only documents pending review can be corrected.",
        )

    extracted_data = dict(document.extracted_data or {})
    submitted = corrections.model_dump(mode="json", exclude_unset=True)
    if "items" in corrections.model_fields_set:
        submitted["items"] = [
            item.model_dump(mode="json") for item in corrections.items
        ]
    values = _invoice_data_for_validation(extracted_data, corrections)
    duplicate = _duplicate_invoice_check(db, values, document)
    values["duplicate"] = duplicate
    result = validate_invoice(values)

    if "original_structured_extraction" not in extracted_data:
        extracted_data["original_structured_extraction"] = extracted_data.get(
            "structured_extraction"
        )
    invoice_index = corrections.invoice_index
    invoice_reviews = extracted_data.get("invoice_reviews")
    if not isinstance(invoice_reviews, dict):
        invoice_reviews = {}
    invoice_reviews[str(invoice_index)] = {
        **(
            invoice_reviews.get(str(invoice_index))
            if isinstance(invoice_reviews.get(str(invoice_index)), dict)
            else {}
        ),
        **submitted,
    }
    extracted_data["invoice_reviews"] = invoice_reviews
    extracted_data["correction_metadata"] = {
        "admin_id": current_admin.id,
        "corrected_at": datetime.now(timezone.utc).isoformat(),
        "invoice_index": invoice_index,
        "fields": sorted(submitted.keys()),
    }
    document.extracted_data = extracted_data
    try:
        _record_document_validation(
            db,
            document,
            current_admin,
            values,
            result,
            action="invoice_document_corrected_and_validated",
        )
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        logger.exception("Document correction failed for %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save document corrections.",
        )
    return _document_detail(document)


def _process_document_record(
    document_id: int,
    db: Session,
    current_admin: AdminUser,
) -> dict:
    document = db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.invoice_id is not None or document.processing_status in {
        "approved", "rejected", "pending_review", "processing"
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document cannot be processed in its current state.",
        )

    storage_root = Path(settings.invoice_storage_dir).resolve()
    file_path = Path(document.storage_path).resolve()
    try:
        file_path.relative_to(storage_root)
    except ValueError as exc:
        logger.error("Stored document path is outside private storage.")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stored document is unavailable for processing.",
        ) from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file is unavailable.")
    if file_path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Maximum upload size is {settings.max_upload_size_mb} MB.",
        )

    data = dict(document.extracted_data or {})
    prior_attempts = data.get("processing_attempts")
    attempts = list(prior_attempts) if isinstance(prior_attempts, list) else []
    attempt = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "admin_id": current_admin.id,
        "status": "processing",
    }
    data["processing_attempts"] = attempts[-19:] + [attempt]
    data["processing_admin_id"] = current_admin.id
    data["processing_started_at"] = attempt["started_at"]
    for key in (
        "validation",
        "validation_input_fingerprint",
        "invoice_validations",
        "invoice_reviews",
        "approved_invoice_indices",
        "approvals",
        "review_status",
        "rejection",
        "structured_invoice",
        "structured_extraction",
        "validated_invoices",
        "fields",
        "corrected_values",
        "reviewed_values",
        "original_structured_extraction",
        "correction_metadata",
        "revision_history",
        "raw_extraction",
        "processing_metadata",
        "warnings",
    ):
        data.pop(key, None)
    document.extracted_data = data
    document.processing_status = "processing"
    db.commit()

    raw_extraction = None
    try:
        file_bytes = file_path.read_bytes()
        extension = Path(document.original_filename).suffix.lower()
        validate_file_signature(file_bytes, extension)
        raw_extraction = extract_uploaded_file(
            file_bytes=file_bytes,
            filename=document.original_filename,
        )
        raw_data = dict(document.extracted_data or {})
        raw_data["raw_extraction"] = raw_extraction
        raw_data["processing_metadata"] = raw_extraction.get("metadata", {})
        document.extracted_data = raw_data
        db.commit()

        structured = document_agent.extract_document(raw_extraction)
        structured_invoices = structured.get("invoices", [])
        if (
            not isinstance(structured_invoices, list)
            or any(not isinstance(invoice, dict) for invoice in structured_invoices)
        ):
            raise ValueError(
                "Local invoice extraction returned an invalid structure."
            )

        updated = dict(document.extracted_data or {})
        updated.update({
            "source_filename": document.original_filename,
            "file_type": extension.lstrip("."),
            "processing_metadata": raw_extraction.get("metadata", {}),
            "structured_extraction": structured,
            "privacy_processing": {
                "mode": structured.get(
                    "processing_mode",
                    "MANUAL_REVIEW_REQUIRED",
                ),
                "ai_called": structured.get("ai_called") is True,
                "outbound_privacy_check_passed": structured.get(
                    "outbound_privacy_check_passed"
                ),
                "sensitive_data_transmitted": (
                    structured.get("sensitive_data_transmitted") is True
                ),
                "manual_review_required": (
                    structured.get("manual_review_required") is True
                ),
                "parser_version": structured.get("parser_version", "privacy-v1"),
                "processing_reason": structured.get(
                    "processing_reason",
                    "Administrator review is required.",
                ),
            },
        })
        warnings = list(raw_extraction.get("warnings", []))
        warnings.extend(structured.get("extraction_notes", []))
        if not structured_invoices:
            public_error = (
                "Automated interpretation was not safe or reliable. "
                "Review the retained source document and retry after correction."
            )
            updated["processing_error"] = public_error
            updated["warnings"] = list(dict.fromkeys(warnings + [public_error]))
            updated["processing_completed_at"] = datetime.now(timezone.utc).isoformat()
            updated["processing_attempts"][-1].update({
                "status": "processing_failed",
                "completed_at": updated["processing_completed_at"],
                "message": public_error,
            })
            document.extracted_data = updated
            document.extraction_notes = "; ".join(updated["warnings"])
            document.processing_status = "processing_failed"
            create_audit_log(
                db=db,
                admin_id=current_admin.id,
                action="invoice_document_processing_failed",
                entity_type="invoice_document",
                entity_id=document.id,
                details={
                    "file_type": extension.lstrip("."),
                    "invoice_count": 0,
                    "record_count": len(raw_extraction.get("records", [])),
                },
            )
            db.commit()
            db.refresh(document)
            return {
                "message": public_error,
                "status": "processing_failed",
                "document": _document_detail(document),
            }

        validated_invoices = []
        for invoice_data in structured_invoices:
            invoice_values = dict(invoice_data)
            invoice_values["amount_aed"] = (
                invoice_data.get("total_amount_aed")
                if invoice_data.get("currency") == "AED"
                else None
            )
            invoice_values["duplicate"] = _duplicate_invoice_check(
                db, invoice_values, document
            )
            invoice_validation = validate_invoice(invoice_values)
            validated_invoices.append({
                **invoice_data,
                "validation": invoice_validation,
            })
        updated["validated_invoices"] = validated_invoices

        selected = structured_invoices[0] if structured_invoices else {}
        if isinstance(selected, dict) and selected:
            fields = {
                key: selected.get(key)
                for key in (
                    "invoice_number", "supplier_name", "supplier_trn",
                    "supplier_address", "supplier_emirate", "customer_name",
                    "customer_email", "customer_trn", "customer_address",
                    "customer_emirate", "currency", "place_of_supply",
                    "issue_date", "supply_date", "due_date", "items",
                    "subtotal_aed", "discount_aed", "vat_amount_aed",
                    "total_amount_aed",
                )
            }
            fields["amount_aed"] = (
                selected.get("total_amount_aed")
                if selected.get("currency") == "AED"
                else None
            )
            updated["structured_invoice"] = selected
            updated["fields"] = fields
            updated["confidence"] = selected.get(
                "extraction_confidence", 0.0
            )
            updated["validation"] = validated_invoices[0]["validation"]
        updated["warnings"] = list(dict.fromkeys(warnings))
        updated["processing_completed_at"] = datetime.now(timezone.utc).isoformat()
        updated["processing_attempts"][-1].update({
            "status": "pending_review",
            "completed_at": updated["processing_completed_at"],
        })
        document.extracted_data = updated
        document.extraction_notes = "; ".join(updated["warnings"]) or None
        document.processing_status = "pending_review"
        create_audit_log(
            db=db,
            admin_id=current_admin.id,
            action="invoice_document_processed",
            entity_type="invoice_document",
            entity_id=document.id,
            details={
                "file_type": extension.lstrip("."),
                "invoice_count": len(structured_invoices),
                "record_count": len(raw_extraction.get("records", [])),
            },
        )
        db.commit()
        db.refresh(document)
        return {
            "message": "Document processed and is ready for administrator review.",
            "status": "pending_review",
            "document": _document_detail(document),
        }
    except Exception as exc:
        db.rollback()
        document = db.get(InvoiceDocument, document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            ) from exc
        failed_data = dict(document.extracted_data or {})
        if raw_extraction is not None:
            failed_data["raw_extraction"] = raw_extraction
            failed_data["processing_metadata"] = raw_extraction.get("metadata", {})
        if isinstance(exc, ValueError):
            public_error = "The document could not be processed. Check its content and retry."
        else:
            public_error = "Document processing failed. The original upload was retained."
        failed_data["processing_error"] = public_error
        failed_data["warnings"] = list(dict.fromkeys(
            list(failed_data.get("warnings", [])) + [public_error]
        ))
        attempts = failed_data.get("processing_attempts")
        if isinstance(attempts, list) and attempts:
            attempts[-1].update({
                "status": "processing_failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "message": public_error,
            })
        document.extracted_data = failed_data
        document.extraction_notes = public_error
        document.processing_status = "processing_failed"
        try:
            create_audit_log(
                db=db,
                admin_id=current_admin.id,
                action="invoice_document_processing_failed",
                entity_type="invoice_document",
                entity_id=document.id,
                details={"error_type": type(exc).__name__},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.error(
                "Failed to persist processing failure for document %s",
                document_id,
            )
        logger.error(
            "Document processing failed for document %s (%s)",
            document_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=public_error,
        ) from exc


@router.post(
    "/{document_id}/process",
    summary="Extract and structure an uploaded document",
)
def process_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Run local-first extraction on an existing upload record."""
    document = db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.processing_status not in {"uploaded", "processing_failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only uploaded or failed documents can be processed.",
        )
    return _process_document_record(document_id, db, current_admin)


@router.post(
    "/{document_id}/retry",
    summary="Retry failed document processing",
)
def retry_document_processing(
    document_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Retry processing without creating a second document record."""
    document = db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.processing_status != "processing_failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only documents with failed processing can be retried.",
        )
    return _process_document_record(document_id, db, current_admin)


def reprocess_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Compatibility helper for earlier internal callers."""
    return process_document(document_id, db, current_admin)


# ---------------------------------------------------------
# 4. Administrator review and invoice approval
# ---------------------------------------------------------

@router.post(
    "/{document_id}/approve",
    response_model=InvoiceReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Approve a validated invoice",
)
@router.post(
    "/{document_id}/review",
    response_model=InvoiceReviewResponse,
    include_in_schema=False,
)
def review_invoice_document(
    document_id: int,
    review: InvoiceReviewRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    """Approve or correct extracted data and save an invoice."""

    document = db.get(
        InvoiceDocument,
        document_id
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )

    if document.processing_status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only documents pending review can be approved.",
        )

    invoice_index = review.invoice_index
    persisted_data = document.extracted_data or {}
    approved_indices = persisted_data.get("approved_invoice_indices", [])
    if not isinstance(approved_indices, list):
        approved_indices = []
    if invoice_index in approved_indices:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice from the document has already been approved."
        )

    extracted_data = document.extracted_data or {}
    values = _invoice_data_for_validation(extracted_data, review)
    duplicate = _duplicate_invoice_check(db, values, document)
    values["duplicate"] = duplicate
    validation = validate_invoice(values)
    invoice_validations = persisted_data.get("invoice_validations")
    invoice_validation = (
        invoice_validations.get(str(invoice_index))
        if isinstance(invoice_validations, dict)
        else None
    )
    persisted_validation = (
        invoice_validation.get("result")
        if isinstance(invoice_validation, dict)
        else persisted_data.get("validation")
    )
    persisted_fingerprint = (
        invoice_validation.get("input_fingerprint")
        if isinstance(invoice_validation, dict)
        else persisted_data.get("validation_input_fingerprint")
    )
    if (
        not isinstance(persisted_validation, dict)
        or persisted_fingerprint != _validation_fingerprint(values)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Validate the latest invoice edits before approval.",
        )
    original_fields = _source_invoice(extracted_data, invoice_index)
    if invoice_index == 0 and isinstance(extracted_data.get("fields"), dict):
        original_fields = {**original_fields, **extracted_data["fields"]}
    if "amount_aed" not in original_fields:
        original_fields["amount_aed"] = original_fields.get("total_amount_aed")
    corrected = invoice_fields_were_corrected(original_fields, review)
    for field in (
        "supplier_name", "supplier_address", "supplier_emirate",
        "supplier_trn", "customer_address", "customer_emirate",
        "customer_trn", "place_of_supply", "currency",
        "supply_date", "subtotal_aed", "discount_aed", "vat_amount_aed",
        "total_amount_aed",
    ):
        new_value = getattr(review, field, None)
        if new_value is not None and str(new_value) != str(original_fields.get(field)):
            corrected = True
    if "items" in review.model_fields_set:
        original_items = original_fields.get("items", [])
        corrected = corrected or (
            [item.model_dump(mode="json") for item in review.items]
            != original_items
        )

    if duplicate["status"] in {
        "same_invoice",
        "conflicting_number",
        "duplicate_upload",
        "duplicate",
        "ambiguous",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=duplicate,
        )
    if not persisted_validation.get("is_valid"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=persisted_validation,
        )
    if not validation["is_valid"]:
        try:
            _record_document_validation(
                db, document, current_admin, values, validation
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Updated validation result could not be saved for %s",
                document_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to save invoice validation results.",
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=validation,
        )

    try:
        _record_document_validation(
            db, document, current_admin, values, validation
        )
        db.flush()
    except Exception:
        db.rollback()
        logger.exception("Invoice validation failed to persist for %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save invoice validation results.",
        )

    review_status = (
        "corrected"
        if corrected
        else "reviewed"
    )

    # Calculate the initial invoice status deterministically.
    invoice_status = (
        "overdue"
        if review.due_date < date.today()
        else "unpaid"
    )

    source_type = Path(document.original_filename).suffix.lower().lstrip(".")

    confidence = extracted_data.get("confidence", 0.0)
    calculated_totals = validation["calculated_totals"]
    approved_items = values.get("items", [])
    has_items = bool(approved_items)
    approved_amount = (
        Decimal(calculated_totals["total_amount_aed"])
        if has_items
        else review.amount_aed.quantize(Decimal("0.01"))
    )
    due_date = parse_invoice_date(review.due_date)
    issue_date = parse_invoice_date(review.issue_date)

    invoice = Invoice(
        invoice_number=review.invoice_number.strip(),
        customer_name=review.customer_name.strip(),
        customer_email=(
            review.customer_email.strip().lower()
            if review.customer_email
            else None
        ),
        amount_aed=approved_amount,
        issue_date=issue_date,
        due_date=due_date,
        status=invoice_status,
        source_type=source_type,
        source_filename=document.original_filename,
        extraction_confidence=float(confidence),
        review_status=review_status,
        notes=review.notes,
        supplier_name=values.get("supplier_name"),
        supplier_address=values.get("supplier_address"),
        supplier_emirate=values.get("supplier_emirate"),
        supplier_trn=values.get("supplier_trn"),
        customer_address=values.get("customer_address"),
        customer_emirate=values.get("customer_emirate"),
        customer_trn=values.get("customer_trn"),
        place_of_supply=values.get("place_of_supply"),
        supply_date=parse_invoice_date(review.supply_date),
        currency=values.get("currency"),
        subtotal_aed=Decimal(calculated_totals["subtotal_aed"]),
        discount_aed=Decimal(calculated_totals["discount_aed"]),
        vat_amount_aed=Decimal(calculated_totals["vat_amount_aed"]),
        total_amount_aed=approved_amount,
        amount_in_words=values.get("amount_in_words"),
        declaration_text=values.get("declaration_text"),
    )

    try:
        db.add(invoice)
        db.flush()

        for item, result in zip(
            approved_items,
            validation["checks"]["line_items"]["results"],
        ):
            calculated = result["calculated"]
            db.add(InvoiceItem(
                invoice_id=invoice.id,
                description=str(item.get("description") or "").strip(),
                quantity=Decimal(result["extracted"]["quantity"]),
                unit=item.get("unit"),
                unit_price_aed=Decimal(result["extracted"]["unit_price_aed"]),
                discount_aed=Decimal(calculated["discount_aed"]),
                taxable_value_aed=Decimal(calculated["taxable_value_aed"]),
                vat_rate=Decimal(result["extracted"]["vat_rate"]),
                vat_amount_aed=Decimal(calculated["vat_amount_aed"]),
                line_total_aed=Decimal(calculated["line_total_aed"]),
            ))

        # A spreadsheet can contain multiple independent invoices.
        if document.invoice_id is None:
            document.invoice_id = invoice.id
        approved_indices.append(invoice_index)
        invoice_count = 1
        structured_extraction = extracted_data.get("structured_extraction")
        if isinstance(structured_extraction, dict):
            extracted_invoices = structured_extraction.get("invoices")
            if isinstance(extracted_invoices, list) and extracted_invoices:
                invoice_count = len(extracted_invoices)
        document.processing_status = (
            "approved" if len(set(approved_indices)) >= invoice_count else "pending_review"
        )
        approval_time = datetime.now(timezone.utc).isoformat()
        approvals = persisted_data.get("approvals")
        if not isinstance(approvals, dict):
            approvals = {}
        approvals[str(invoice_index)] = {
            "admin_id": current_admin.id,
            "approved_at": approval_time,
            "invoice_id": invoice.id,
        }
        document.extracted_data = {
            **persisted_data,
            "approved_invoice_indices": sorted(set(approved_indices)),
            "approvals": approvals,
            "review_status": (
                "approved"
                if document.processing_status == "approved"
                else "partially_approved"
            ),
            "validation": validation,
        }

        create_audit_log(
            db=db,
            admin_id=current_admin.id,
            action="invoice_approved",
            entity_type="invoice",
            entity_id=invoice.id,
            details={
                "document_id": document.id,
                "invoice_index": invoice_index,
                "invoice_number": invoice.invoice_number,
                "review_status": review_status,
                "source_type": source_type,
                "validation_error_count": len(validation["errors"]),
                "validation_warning_count": len(validation["warnings"]),
                "line_item_count": len(approved_items),
            }
        )

        document.extraction_notes = (
            f"Administrator reviewed and approved. "
            f"Review status: {review_status}."
        )

        db.commit()
        db.refresh(invoice)

        return InvoiceReviewResponse(
            message="Invoice successfully reviewed and saved.",
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            review_status=invoice.review_status,
            status=invoice.status,
            amount_aed=str(invoice.amount_aed)
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Invoice review failed for document %s",
            document_id
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the reviewed invoice."
        )
