from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class UAEInvoiceItemSchema(BaseModel):
    """One goods or services row from an invoice."""

    model_config = ConfigDict(extra="ignore")

    description: str = Field(
        min_length=1,
        max_length=500,
    )

    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=14,
        decimal_places=3,
    )

    unit: str | None = Field(
        default=None,
        max_length=40,
    )

    unit_price_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    discount_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    taxable_value_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    vat_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )

    vat_amount_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    line_total_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

class UAEInvoiceExtractionSchema(BaseModel):
    """
    Structured invoice data extracted by the AI agent.

    Extracted information must be reviewed before
    being saved as an approved invoice.
    """

    model_config = ConfigDict(extra="ignore")

    invoice_number: str | None = Field(
        default=None,
        max_length=100,
    )

    supplier_name: str | None = Field(
        default=None,
        max_length=180,
    )

    supplier_address: str | None = None

    supplier_emirate: str | None = Field(
        default=None,
        max_length=80,
    )

    supplier_trn: str | None = Field(
        default=None,
        max_length=30,
    )

    customer_name: str | None = Field(
        default=None,
        max_length=180,
    )

    customer_address: str | None = None

    customer_email: str | None = Field(
        default=None,
        max_length=180,
    )

    customer_emirate: str | None = Field(
        default=None,
        max_length=80,
    )

    customer_trn: str | None = Field(
        default=None,
        max_length=30,
    )

    issue_date: date | None = None
    supply_date: date | None = None
    due_date: date | None = None

    place_of_supply: str | None = Field(
        default=None,
        max_length=150,
    )

    invoice_type: str | None = None

    currency: str | None = Field(
        default=None,
        max_length=20,
    )

    items: list[UAEInvoiceItemSchema] = Field(
        default_factory=list,
    )

    subtotal_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    discount_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    vat_amount_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    total_amount_aed: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )

    amount_in_words: str | None = None
    declaration_text: str | None = None

    extraction_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    extraction_notes: list[str] = Field(
        default_factory=list,
    )

    missing_fields: list[str] = Field(default_factory=list)

    document_classification: Literal[
        "single_invoice",
        "multiple_invoices",
        "invoice_line_items",
        "invoice_register",
        "unknown",
    ] = "unknown"

    source_filename: str | None = None
    source_worksheet: str | None = None
    source_page: int | None = None
    source_row: int | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class UAEInvoiceReviewSchema(UAEInvoiceExtractionSchema):
    """Invoice data reviewed by the administrator."""

    review_notes: str | None = None


class UAEInvoiceResponseSchema(UAEInvoiceExtractionSchema):
    """Invoice response returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class TRNValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None
    is_present: bool
    is_valid_format: bool
    message: str


class FieldValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: str | None = None
    is_valid: bool
    message: str


class InvoiceItemCalculationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    description: str
    extracted: dict[str, str | None]
    calculated: dict[str, str | None]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InvoiceTotalsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtotal_aed: Decimal | None
    discount_aed: Decimal | None
    vat_amount_aed: Decimal | None
    total_amount_aed: Decimal | None
    invoice_discount_allocation_method: str


class CompleteInvoiceValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    review_required: bool
    errors: list[str]
    warnings: list[str]
    checks: dict[str, Any]
    calculated_totals: InvoiceTotalsResult
