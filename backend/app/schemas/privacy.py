from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AllowedInvoiceField = Literal[
    "invoice_number",
    "supplier_name",
    "supplier_trn",
    "supplier_address",
    "supplier_emirate",
    "customer_name",
    "customer_trn",
    "customer_address",
    "customer_email",
    "customer_emirate",
    "issue_date",
    "supply_date",
    "due_date",
    "currency",
    "description",
    "quantity",
    "unit",
    "unit_price_aed",
    "discount_aed",
    "subtotal_aed",
    "taxable_value_aed",
    "vat_rate",
    "vat_amount_aed",
    "line_total_aed",
    "total_amount_aed",
    "place_of_supply",
    "payment_status",
]


class AIColumnMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_name: str
    field_name: AllowedInvoiceField
    confidence: float = Field(ge=0, le=1)


class AIColumnMappingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[AIColumnMapping]
    warnings: list[str] = Field(default_factory=list)


class AIInterpretationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str
    interpreted_labels: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
