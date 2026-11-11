
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models import AdminUser, AuditLog, Invoice
from app.schemas.invoice import InvoiceCorrectionRequest, InvoiceStatusUpdate
from app.schemas.records import InvoiceOut


logger = logging.getLogger(__name__)

# Invoice routes protected by JWT authentication
router = APIRouter(
    prefix="/api/invoices",
    tags=["Invoices"],
    dependencies=[Depends(get_current_admin)]
)


# Retrieve all invoices
@router.get("", response_model=list[InvoiceOut])
def get_all_invoices(
    db: Session = Depends(get_db)
):
    statement = (
        select(Invoice)
        .order_by(Invoice.due_date.asc())
    )

    invoices = db.scalars(statement).all()

    return invoices


# Retrieve overdue invoices
@router.get("/overdue", response_model=list[InvoiceOut])
def get_overdue_invoices(
    db: Session = Depends(get_db)
):
    today = date.today()

    statement = (
        select(Invoice)
        .where(
            Invoice.status != "paid",
            Invoice.due_date < today
        )
        .order_by(Invoice.due_date.asc())
    )

    invoices = db.scalars(statement).all()

    return invoices


# Retrieve a specific invoice
@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found"
        )

    return invoice


@router.patch("/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    update: InvoiceStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    previous_status = invoice.status
    next_status = update.status
    if previous_status == next_status:
        return invoice
    if previous_status not in {"paid", "unpaid", "overdue"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice status '{previous_status}' cannot be changed here.",
        )

    invoice.status = (
        "overdue"
        if next_status == "unpaid" and invoice.due_date < date.today()
        else next_status
    )
    try:
        db.add(AuditLog(
            admin_id=current_admin.id,
            action="invoice_payment_status_changed",
            entity_type="invoice",
            entity_id=invoice.id,
            details={
                "previous_status": previous_status,
                "new_status": invoice.status,
                "method": "manual_status_only",
            },
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        db.refresh(invoice)
    except Exception as exc:
        db.rollback()
        logger.exception("Invoice status update failed for %s", invoice_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update invoice payment status.",
        ) from exc
    return invoice


@router.patch("/{invoice_id}/correction", response_model=InvoiceOut)
def correct_approved_invoice(
    invoice_id: int,
    correction: InvoiceCorrectionRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.review_status not in {"reviewed", "corrected"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved, reviewed invoices can be corrected.",
        )

    changes = correction.model_dump(exclude={"reason"}, exclude_unset=True)
    if "invoice_number" in changes:
        changes["invoice_number"] = changes["invoice_number"].strip()
        existing_id = db.scalar(
            select(Invoice.id).where(
                func.lower(Invoice.invoice_number)
                == changes["invoice_number"].lower(),
                Invoice.id != invoice.id,
            )
        )
        if existing_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That invoice number is already assigned to another invoice.",
            )
    if "customer_name" in changes:
        changes["customer_name"] = changes["customer_name"].strip()
    if "customer_email" in changes and changes["customer_email"]:
        changes["customer_email"] = changes["customer_email"].strip().lower()

    effective_issue_date = changes.get("issue_date", invoice.issue_date)
    effective_due_date = changes.get("due_date", invoice.due_date)
    if effective_due_date < effective_issue_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Due date cannot be earlier than the issue date.",
        )

    before = {
        field: getattr(invoice, field)
        for field in changes
    }
    after = {
        field: value.isoformat() if isinstance(value, date) else value
        for field, value in changes.items()
    }
    before_serialized = {
        field: value.isoformat() if isinstance(value, date) else value
        for field, value in before.items()
    }
    try:
        for field, value in changes.items():
            setattr(invoice, field, value)
        invoice.review_status = "corrected"
        db.add(AuditLog(
            admin_id=current_admin.id,
            action="approved_invoice_corrected",
            entity_type="invoice",
            entity_id=invoice.id,
            details={
                "reason": correction.reason.strip(),
                "before": before_serialized,
                "after": after,
            },
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        db.refresh(invoice)
    except Exception as exc:
        db.rollback()
        logger.exception("Approved invoice correction failed for %s", invoice_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the invoice correction.",
        ) from exc
    return invoice
