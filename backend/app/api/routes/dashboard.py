
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models import Invoice


# Dashboard routes protected by JWT authentication
router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_admin)]
)


# Retrieve dashboard financial summary
@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db)
):
    statement = (
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .order_by(Invoice.id)
    )

    invoices = db.scalars(statement).all()

    today = date.today()

    total_invoices = len(invoices)

    paid_count = 0
    unpaid_count = 0
    overdue_count = 0

    total_outstanding = Decimal("0.00")

    for invoice in invoices:

        if invoice.status == "paid":
            paid_count += 1
            continue

        unpaid_count += 1

        amount_paid = sum(
            (
                payment.amount_aed
                for payment in invoice.payments
            ),
            Decimal("0.00")
        )

        outstanding = max(
            invoice.amount_aed - amount_paid,
            Decimal("0.00")
        )

        total_outstanding += outstanding

        if invoice.due_date < today and outstanding > 0:
            overdue_count += 1

    return {
        "invoice_count": total_invoices,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "overdue_count": overdue_count,
        "outstanding_aed": str(
            total_outstanding.quantize(Decimal("0.01"))
        ),
        "currency": "AED",
        "data_label": "Synthetic demo data"
    }
