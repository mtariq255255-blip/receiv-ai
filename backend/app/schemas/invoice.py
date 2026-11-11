
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvoiceExtractedFields(BaseModel):
    invoice_number: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    amount_aed: str | None = None
    currency: str | None = None
    issue_date: str | None = None
    due_date: str | None = None
    notes: str | None = None


class InvoiceReviewItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    description: str | None = Field(default=None, max_length=500)
    quantity: Decimal | None = Field(default=None, max_digits=14, decimal_places=3)
    unit: str | None = Field(default=None, max_length=40)
    unit_price_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    discount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    taxable_value_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    vat_rate: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    vat_amount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    line_total_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)


class InvoiceValidationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    invoice_number: str | None = Field(default=None, max_length=100)
    supplier_name: str | None = Field(default=None, max_length=180)
    supplier_address: str | None = None
    supplier_emirate: str | None = Field(default=None, max_length=80)
    supplier_trn: str | None = Field(default=None, max_length=30)
    customer_name: str | None = Field(default=None, max_length=180)
    customer_email: str | None = Field(default=None, max_length=255)
    customer_address: str | None = None
    customer_emirate: str | None = Field(default=None, max_length=80)
    customer_trn: str | None = Field(default=None, max_length=30)
    currency: str | None = Field(default=None, max_length=20)
    place_of_supply: str | None = Field(default=None, max_length=150)
    invoice_index: int = Field(default=0, ge=0)
    issue_date: str | date | None = None
    supply_date: str | date | None = None
    due_date: str | date | None = None
    amount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    subtotal_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    discount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    vat_amount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_amount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    items: list[InvoiceReviewItem] = Field(default_factory=list, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)


class InvoiceReviewRequest(InvoiceValidationRequest):
    invoice_number: str = Field(min_length=1, max_length=100)
    customer_name: str = Field(min_length=1, max_length=180)
    customer_email: str | None = Field(default=None, max_length=180)

    amount_aed: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2
    )

    issue_date: date
    due_date: date
    supply_date: date | None = None

    notes: str | None = Field(default=None, max_length=2000)

    subtotal_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    discount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    vat_amount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_amount_aed: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)

    @model_validator(mode="after")
    def validate_invoice_dates(self):
        if self.due_date < self.issue_date:
            raise ValueError(
                "Due date cannot be earlier than the issue date."
            )

        if self.customer_email:
            import re

            email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

            if not re.match(email_pattern, self.customer_email):
                raise ValueError("Invalid customer email address.")

        return self


class InvoiceReviewResponse(BaseModel):
    message: str
    invoice_id: int
    invoice_number: str
    review_status: str
    status: str
    amount_aed: str


class InvoiceStatusUpdate(BaseModel):
    status: str = Field(pattern="^(paid|unpaid)$")


class InvoiceCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=2000)
    invoice_number: str | None = Field(default=None, min_length=1, max_length=100)
    customer_name: str | None = Field(default=None, min_length=1, max_length=180)
    customer_email: str | None = Field(default=None, max_length=180)
    supplier_name: str | None = Field(default=None, max_length=180)
    supplier_trn: str | None = Field(default=None, max_length=30)
    issue_date: date | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_correction(self):
        editable_fields = self.model_fields_set - {"reason"}
        if not editable_fields:
            raise ValueError("Provide at least one invoice field to correct.")
        if (
            self.issue_date is not None
            and self.due_date is not None
            and self.due_date < self.issue_date
        ):
            raise ValueError("Due date cannot be earlier than the issue date.")
        return self
