import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CENT = Decimal("0.01")
QUANTITY_PRECISION = Decimal("0.001")
RATE_PRECISION = Decimal("0.01")
ZERO = Decimal("0.00")
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d/%m/%Y %H:%M",
)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "")
    if text.upper().startswith("AED"):
        text = text[3:].strip()
    elif text.upper().endswith("AED"):
        text = text[:-3].strip()
    if text.startswith("د.إ"):
        text = text[3:].strip()
    elif text.endswith("د.إ"):
        text = text[:-3].strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    try:
        return str(value.quantize(CENT, rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None


def parse_invoice_date(value: Any) -> date | None:
    """Parse supported UAE invoice date formats without changing the source value."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def parse_invoice_amount(value: Any) -> Decimal | None:
    """Convert an amount to a two-decimal Decimal using ROUND_HALF_UP."""
    amount = _decimal(value)
    if amount is None:
        return None
    try:
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def validate_trn(trn: str | None) -> dict[str, Any]:
    """Check UAE TRN formatting only; this does not verify FTA registration."""
    if trn is None or not str(trn).strip():
        return {
            "value": None,
            "is_present": False,
            "is_valid_format": False,
            "message": "Supplier or buyer TRN was not provided.",
        }

    original = str(trn).strip()
    normalized = re.sub(r"[\s-]", "", original)
    valid = len(normalized) == 15 and normalized.isascii() and normalized.isdigit()
    return {
        "value": normalized,
        "is_present": True,
        "is_valid_format": valid,
        "message": (
            "TRN format is valid; official FTA registration was not checked."
            if valid
            else "TRN must contain exactly 15 digits."
        ),
    }


def calculate_invoice_item(item: dict[str, Any]) -> dict[str, Any]:
    """Calculate line values with Decimal arithmetic and two-place half-up rounding."""
    errors: list[str] = []
    warnings: list[str] = []
    quantity = _decimal(item.get("quantity"))
    unit_price = _decimal(item.get("unit_price_aed"))
    raw_discount = item.get("discount_aed")
    parsed_discount = _decimal(raw_discount)
    discount = parsed_discount if parsed_discount is not None else ZERO
    vat_rate = _decimal(item.get("vat_rate"))
    try:
        quantity = (
            quantity.quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_UP)
            if quantity is not None
            else None
        )
        unit_price = (
            unit_price.quantize(CENT, rounding=ROUND_HALF_UP)
            if unit_price is not None
            else None
        )
        discount = discount.quantize(CENT, rounding=ROUND_HALF_UP)
        vat_rate = (
            vat_rate.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)
            if vat_rate is not None
            else None
        )
    except InvalidOperation:
        errors.append("Line item values exceed supported precision.")
        quantity = None
        unit_price = None

    if not str(item.get("description") or "").strip():
        errors.append("Line item description is required.")
    if quantity is None:
        errors.append("Line item quantity is missing or invalid.")
    elif quantity <= 0:
        errors.append("Line item quantity must be greater than zero.")
    if unit_price is None:
        errors.append("Line item unit price is missing or invalid.")
    elif unit_price < 0:
        errors.append("Line item unit price cannot be negative.")
    if raw_discount not in (None, "") and parsed_discount is None:
        errors.append("Line item discount is not a valid number.")
    if discount < 0:
        errors.append("Line item discount cannot be negative.")
    for field in ("taxable_value_aed", "vat_amount_aed", "line_total_aed"):
        raw_value = item.get(field)
        parsed_value = _decimal(raw_value)
        if raw_value not in (None, "") and parsed_value is None:
            errors.append(f"Extracted {field.replace('_', ' ')} is not a valid number.")
        elif parsed_value is not None and parsed_value < 0:
            errors.append(f"Extracted {field.replace('_', ' ')} cannot be negative.")
    if vat_rate is None:
        errors.append("Line item VAT rate is missing or invalid.")
    elif vat_rate < 0 or vat_rate > 100:
        errors.append("Line item VAT rate must be between 0 and 100.")
    elif vat_rate not in (Decimal("0"), Decimal("5")):
        warnings.append(
            "VAT rate is not the common 0% or 5% rate; confirm the stated treatment."
        )

    extracted = {
        key: _money(_decimal(item.get(key)))
        for key in (
            "discount_aed",
            "taxable_value_aed",
            "vat_amount_aed",
            "line_total_aed",
        )
    }
    if quantity is not None:
        try:
            extracted["quantity"] = str(
                quantity.quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_UP)
            )
        except InvalidOperation:
            extracted["quantity"] = str(quantity)
    if unit_price is not None:
        extracted["unit_price_aed"] = _money(unit_price)
    if vat_rate is not None:
        extracted["vat_rate"] = str(vat_rate)

    calculated: dict[str, str | None] = {
        "gross_value_aed": None,
        "discount_aed": _money(discount),
        "taxable_value_aed": None,
        "vat_amount_aed": None,
        "line_total_aed": None,
    }
    if errors:
        return {
            "is_valid": False,
            "description": str(item.get("description") or ""),
            "extracted": extracted,
            "calculated": calculated,
            "errors": errors,
            "warnings": warnings,
        }

    gross = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
    if discount > gross:
        errors.append("Line item discount cannot exceed its gross value.")
        return {
            "is_valid": False,
            "description": str(item.get("description") or ""),
            "extracted": extracted,
            "calculated": calculated,
            "errors": errors,
            "warnings": warnings,
        }

    taxable = (gross - discount).quantize(CENT, rounding=ROUND_HALF_UP)
    vat_amount = (taxable * vat_rate / Decimal("100")).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    line_total = (taxable + vat_amount).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    calculated = {
        "gross_value_aed": _money(gross),
        "discount_aed": _money(discount),
        "taxable_value_aed": _money(taxable),
        "vat_amount_aed": _money(vat_amount),
        "line_total_aed": _money(line_total),
    }

    for field in ("taxable_value_aed", "vat_amount_aed", "line_total_aed"):
        observed = _decimal(item.get(field))
        expected = {
            "taxable_value_aed": taxable,
            "vat_amount_aed": vat_amount,
            "line_total_aed": line_total,
        }[field]
        if observed is not None and observed.quantize(
            CENT, rounding=ROUND_HALF_UP
        ) != expected:
            warnings.append(
                f"Calculated {field.replace('_', ' ')} differs from the extracted value."
            )
    return {
        "is_valid": not errors,
        "description": str(item.get("description") or ""),
        "extracted": extracted,
        "calculated": calculated,
        "errors": errors,
        "warnings": warnings,
    }


def calculate_invoice_totals(
    items: list[dict[str, Any]],
    invoice_discount_aed: Any = None,
) -> dict[str, Any]:
    """Sum calculated lines and apply a distinct invoice-level discount once."""
    line_results = [calculate_invoice_item(item) for item in items]
    subtotal = sum(
        (
            _decimal(result["calculated"]["taxable_value_aed"]) or ZERO
            for result in line_results
        ),
        ZERO,
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    line_discount = sum(
        (_decimal(result["calculated"]["discount_aed"]) or ZERO for result in line_results),
        ZERO,
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    vat = sum(
        (
            _decimal(result["calculated"]["vat_amount_aed"]) or ZERO
            for result in line_results
        ),
        ZERO,
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    invoice_discount = _decimal(invoice_discount_aed) or ZERO
    invoice_discount = invoice_discount.quantize(CENT, rounding=ROUND_HALF_UP)
    warnings: list[str] = []

    if invoice_discount < 0:
        warnings.append("Invoice-level discount cannot be negative.")
        invoice_discount = ZERO
        allocation = "invalid_invoice_discount"
    elif invoice_discount and invoice_discount == line_discount:
        allocation = "included_in_line_discounts"
    elif invoice_discount:
        allocation = "separate_invoice_adjustment_after_line_vat"
        warnings.append(
            "A distinct invoice-level discount was deducted after line VAT; "
            "confirm the discount allocation against the source invoice."
        )
    else:
        allocation = "line_discounts_only"

    discount_total = line_discount
    total = sum(
        (
            _decimal(result["calculated"]["line_total_aed"]) or ZERO
            for result in line_results
        ),
        ZERO,
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    if invoice_discount and allocation != "included_in_line_discounts":
        discount_total += invoice_discount
        total -= invoice_discount

    return {
        "subtotal_aed": _money(subtotal),
        "discount_aed": _money(discount_total),
        "vat_amount_aed": _money(vat),
        "total_amount_aed": _money(total),
        "invoice_discount_allocation_method": allocation,
        "line_items": line_results,
        "warnings": warnings,
    }


def validate_invoice(data: dict[str, Any]) -> dict[str, Any]:
    """Validate extracted or administrator-corrected invoice data without approval."""
    errors: list[str] = []
    warnings: list[str] = []
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
        errors.append("Line item data is invalid.")

    required = (
        ("invoice_number", "Invoice number is required."),
        ("supplier_name", "Supplier name is required."),
        ("customer_name", "Customer name is required."),
    )
    for key, message in required:
        if not str(data.get(key) or "").strip():
            errors.append(message)

    customer_email = data.get("customer_email")
    if customer_email and not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", str(customer_email).strip()
    ):
        errors.append("Customer email format is invalid.")

    dates: dict[str, Any] = {}
    parsed_dates: dict[str, date | None] = {}
    for key, label in (
        ("issue_date", "Issue date"),
        ("supply_date", "Supply date"),
        ("due_date", "Due date"),
    ):
        value = data.get(key)
        parsed = parse_invoice_date(value)
        parsed_dates[key] = parsed
        dates[key] = {
            "value": str(value) if value not in (None, "") else None,
            "is_valid": parsed is not None if value not in (None, "") else None,
        }
        if value not in (None, "") and parsed is None:
            errors.append(f"{label} is not a valid supported calendar date.")
        elif key == "issue_date" and parsed is None:
            errors.append("Issue date is required.")
        elif key != "issue_date" and parsed is None:
            warnings.append(f"{label} was not provided.")

    issue_date = parsed_dates["issue_date"]
    due_date = parsed_dates["due_date"]
    supply_date = parsed_dates["supply_date"]
    if issue_date and due_date and due_date < issue_date:
        errors.append("Due date cannot be earlier than invoice issue date.")
    if supply_date and issue_date and supply_date < issue_date:
        warnings.append("Supply date is earlier than the invoice issue date; confirm it.")
    if supply_date and due_date and supply_date > due_date:
        warnings.append("Supply date is later than the due date; confirm it.")

    supplier_trn = validate_trn(data.get("supplier_trn"))
    customer_trn = validate_trn(data.get("customer_trn"))
    for label, result in (("Supplier", supplier_trn), ("Buyer", customer_trn)):
        if result["is_present"] and not result["is_valid_format"]:
            warnings.append(f"{label} TRN must contain 15 digits.")
        elif not result["is_present"]:
            warnings.append(f"{label} TRN was not provided.")

    currency = str(data.get("currency") or "").strip().upper()
    currency_check = {
        "value": currency or None,
        "is_present": bool(currency),
        "is_supported_for_aed_ledger": currency == "AED",
    }
    if not currency:
        errors.append("Currency is missing. Confirm the invoice currency.")
        warnings.append("Currency is missing. Confirm the invoice currency.")
    elif currency != "AED":
        errors.append(
            "Only AED invoices can be approved into the AED invoice register; "
            "foreign-currency conversion is not performed."
        )

    if not items:
        warnings.append(
            "No line items were provided; the clearly stated invoice total will be used."
        )

    raw_invoice_discount = data.get("discount_aed")
    if raw_invoice_discount not in (None, "") and _decimal(raw_invoice_discount) is None:
        errors.append("Invoice-level discount is not a valid number.")
    elif _decimal(raw_invoice_discount) is not None and _decimal(raw_invoice_discount) < 0:
        errors.append("Invoice-level discount cannot be negative.")
    totals = calculate_invoice_totals(items, raw_invoice_discount)
    expected_subtotal = _decimal(data.get("subtotal_aed"))
    expected_vat = _decimal(data.get("vat_amount_aed"))
    review_amount = _decimal(data.get("amount_aed"))
    expected_total = _decimal(
        data.get("total_amount_aed")
        if data.get("total_amount_aed") is not None
        else review_amount
    )
    for field in ("subtotal_aed", "vat_amount_aed", "total_amount_aed", "amount_aed"):
        value = _decimal(data.get(field))
        if data.get(field) not in (None, "") and value is None:
            errors.append(f"{field.replace('_', ' ').capitalize()} is not a valid amount.")
        elif value is not None and value < 0:
            errors.append(f"{field.replace('_', ' ').capitalize()} cannot be negative.")
    if not items:
        totals.update({
            "subtotal_aed": _money(expected_subtotal or ZERO),
            "discount_aed": _money(_decimal(data.get("discount_aed")) or ZERO),
            "vat_amount_aed": _money(expected_vat or ZERO),
            "total_amount_aed": _money(expected_total or ZERO),
            "invoice_discount_allocation_method": "stated_invoice_totals_no_line_items",
        })
        if (
            expected_subtotal is not None
            and expected_vat is not None
            and expected_total is not None
        ):
            expected_from_components = (
                expected_subtotal
                + expected_vat
                - (_decimal(data.get("discount_aed")) or ZERO)
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            if expected_from_components != expected_total.quantize(
                CENT, rounding=ROUND_HALF_UP
            ):
                errors.append(
                    "Stated subtotal, discount, VAT and invoice total do not reconcile."
                )
                warnings.append(
                    "Invoice totals cannot be independently recalculated without line items."
                )

    line_errors = [
        message for row in totals["line_items"] for message in row["errors"]
    ]
    line_warnings = [
        message for row in totals["line_items"] for message in row["warnings"]
    ]
    errors.extend(line_errors)
    warnings.extend(line_warnings)
    warnings.extend(totals["warnings"])

    comparisons: dict[str, Any] = {}
    for field, expected in (
        ("subtotal_aed", expected_subtotal),
        ("vat_amount_aed", expected_vat),
        ("total_amount_aed", expected_total),
    ):
        calculated = _decimal(totals[field])
        matches = (
            None
            if expected is None or not items
            else expected.quantize(CENT, rounding=ROUND_HALF_UP) == calculated
        )
        comparisons[field] = {
            "extracted": _money(expected),
            "calculated": totals[field],
            "matches": matches,
        }
        if expected is not None and items and not matches:
            errors.append(
                f"Calculated {field.replace('_', ' ')} differs from the extracted value."
            )

    review_amount_matches = (
        None
        if review_amount is None or not items
        else review_amount.quantize(CENT, rounding=ROUND_HALF_UP)
        == _decimal(totals["total_amount_aed"])
    )
    comparisons["amount_aed"] = {
        "extracted": _money(review_amount),
        "calculated": totals["total_amount_aed"] if items else None,
        "matches": review_amount_matches,
    }
    if items and review_amount is not None and not review_amount_matches:
        errors.append("Calculated grand total differs from the reviewed invoice amount.")

    if expected_total is None or expected_total <= 0:
        errors.append("A positive invoice total is required.")

    if items and not errors and expected_total is None:
        errors.append("A clearly identified invoice total is required.")

    duplicate = data.get("duplicate") or {
        "status": "not_checked",
        "message": "Duplicate invoice status has not been checked.",
    }
    duplicate_conflict = duplicate.get("status") in {
        "same_invoice",
        "conflicting_number",
        "duplicate_upload",
        "duplicate",
    }
    if duplicate_conflict:
        errors.append(
            duplicate.get("message", "An existing invoice conflict was found.")
        )
    elif duplicate.get("status") == "ambiguous":
        warnings.append(
            duplicate.get("message", "Invoice number needs duplicate review.")
        )

    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    return {
        "is_valid": not errors,
        "review_required": bool(
            errors
            or warnings
            or duplicate_conflict
            or duplicate.get("status") == "ambiguous"
        ),
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "dates": dates,
            "supplier_trn": supplier_trn,
            "customer_trn": customer_trn,
            "currency": currency_check,
            "line_items": {
                "count": len(items),
                "results": totals["line_items"],
                "is_valid": not line_errors,
            },
            "vat": {
                "calculated_vat_aed": totals["vat_amount_aed"],
                "extracted_vat_aed": _money(expected_vat),
                "matches": comparisons["vat_amount_aed"]["matches"],
            },
            "totals": comparisons,
            "duplicate": duplicate,
        },
        "calculated_totals": {
            key: totals[key]
            for key in (
                "subtotal_aed",
                "discount_aed",
                "vat_amount_aed",
                "total_amount_aed",
                "invoice_discount_allocation_method",
            )
        },
    }


def validate_extracted_fields(fields: dict) -> dict:
    """Backwards-compatible validation for legacy CSV invoice rows."""
    errors = []
    missing_fields = []
    for field in ("invoice_number", "customer_name", "amount_aed", "issue_date"):
        value = fields.get(field)
        if value is None or str(value).strip() == "":
            missing_fields.append(field)

    invoice_number = fields.get("invoice_number")
    customer_name = fields.get("customer_name")
    if invoice_number and len(str(invoice_number).strip()) > 100:
        errors.append("Invoice number exceeds 100 characters.")
    if customer_name and len(str(customer_name).strip()) > 200:
        errors.append("Customer name exceeds 200 characters.")

    amount = parse_invoice_amount(fields.get("amount_aed"))
    if fields.get("amount_aed") and amount is None:
        errors.append("Invoice amount is not a valid number.")
    elif amount is not None and amount <= 0:
        errors.append("Invoice amount must be greater than zero.")

    issue_date = parse_invoice_date(fields.get("issue_date"))
    due_date = parse_invoice_date(fields.get("due_date"))
    if fields.get("issue_date") and issue_date is None:
        errors.append("Issue date format is invalid.")
    if fields.get("due_date") and due_date is None:
        errors.append("Due date format is invalid.")
    if issue_date and due_date and due_date < issue_date:
        errors.append("Due date cannot be earlier than issue date.")

    customer_email = fields.get("customer_email")
    if customer_email and not re.match(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(customer_email).strip()
    ):
        errors.append("Customer email format is invalid.")

    return {
        "valid": not errors and not missing_fields,
        "errors": errors,
        "missing_fields": missing_fields,
        "normalised": {
            "amount_aed": _money(amount),
            "issue_date": issue_date.isoformat() if issue_date else None,
            "due_date": due_date.isoformat() if due_date else None,
        },
    }
