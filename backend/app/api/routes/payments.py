
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models import Payment
from app.schemas.records import PaymentOut


# Payment routes protected by JWT authentication
router = APIRouter(
    prefix="/api/payments",
    tags=["Payments"],
    dependencies=[Depends(get_current_admin)]
)


# Retrieve all payments
@router.get("", response_model=list[PaymentOut])
def get_all_payments(
    db: Session = Depends(get_db)
):
    statement = (
        select(Payment)
        .order_by(Payment.payment_date.desc())
    )

    payments = db.scalars(statement).all()

    return payments
