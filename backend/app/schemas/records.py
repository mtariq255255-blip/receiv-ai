from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class InvoiceOut(BaseModel):

    id: int
    invoice_number: str
    customer_name: str
    customer_email: str | None

    amount_aed: Decimal

    issue_date: date
    due_date: date

    status: str
    source_type: str
    review_status: str

    model_config = ConfigDict(
        from_attributes=True
    )


class PaymentOut(BaseModel):

    id: int
    invoice_id: int

    amount_aed: Decimal
    payment_date: date

    payment_reference: str | None
    notes: str | None

    model_config = ConfigDict(
        from_attributes=True
    )