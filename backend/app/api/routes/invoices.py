
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models import Invoice
from app.schemas.records import InvoiceOut


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
