import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from pydantic import ValidationError

from app.schemas.uae_invoice import UAEInvoiceExtractionSchema


CENT = Decimal("0.01")
PARTY_LABELS = {
    "supplier": ("supplier", "vendor", "seller", "bill from", "from"),
    "buyer": ("buyer", "customer", "client", "bill to"),
}
EMIRATES = (
    "Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain",
    "Ras Al Khaimah", "Fujairah",
)
METADATA_LABELS = {
    "invoice number": "invoice_number",
    "invoice no": "invoice_number",
    "invoice": "invoice_number",
    "tax invoice number": "invoice_number",
    "invoice date": "issue_date",
    "issue date": "issue_date",
    "supply date": "supply_date",
    "date of supply": "supply_date",
    "due date": "due_date",
    "payment due": "due_date",
    "payment due date": "due_date",
    "currency": "currency",
    "currency code": "currency",
    "place of supply": "place_of_supply",
}
SUMMARY_LABELS = {
    "subtotal before discount": "subtotal_before_discount_aed",
    "sub total before discount": "subtotal_before_discount_aed",
    "subtotal": "subtotal_before_discount_aed",
    "sub total": "subtotal_before_discount_aed",
    "discount": "discount_aed",
    "total discount": "discount_aed",
    "taxable amount": "subtotal_aed",
    "taxable value": "subtotal_aed",
    "vat": "vat_amount_aed",
    "vat amount": "vat_amount_aed",
    "total vat": "vat_amount_aed",
    "grand total": "total_amount_aed",
    "invoice total": "total_amount_aed",
    "total payable": "total_amount_aed",
    "amount due": "total_amount_aed",
}
ITEM_LABELS = {
    "description": "description",
    "item description": "description",
    "product description": "description",
    "service description": "description",
    "qty": "quantity",
    "quantity": "quantity",
    "unit": "unit",
    "unit of measure": "unit",
    "unit price": "unit_price_aed",
    "price per unit": "unit_price_aed",
    "discount": "discount_aed",
    "discount amount": "discount_aed",
    "taxable": "taxable_value_aed",
    "taxable amount": "taxable_value_aed",
    "taxable value": "taxable_value_aed",
    "vat": "vat_amount_aed",
    "vat amount": "vat_amount_aed",
    "vat rate": "vat_rate",
    "vat %": "vat_rate",
    "vat rate %": "vat_rate",
    "amount": "line_total_aed",
    "line total": "line_total_aed",
    "line total amount": "line_total_aed",
}


def _normalized_label(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return " ".join(text.split())


def _decimal(value: Any, precision: Decimal = CENT) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    text = re.sub(r"^(?:AED|د\.إ)\s*", "", text, flags=re.I)
    text = re.sub(r"\s*(?:AED|د\.إ)$", "", text, flags=re.I)
    text = text.strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        return None
    try:
        number = Decimal(text)
        if not number.is_finite():
            return None
        return number.quantize(precision, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for date_format in (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y",
        "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    ):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def _rows(table: dict) -> list[list[str]]:
    source = table.get("rows")
    if isinstance(source, list):
        return [
            [str(value or "").strip() for value in row]
            for row in source
            if isinstance(row, list)
        ]
    cells = table.get("cells")
    if not isinstance(cells, list):
        return []
    result: list[list[str]] = []
    for row in cells:
        if isinstance(row, list):
            result.append([
                str(cell.get("text") or "").strip()
                if isinstance(cell, dict)
                else str(cell or "").strip()
                for cell in row
            ])
    return result


def _label_field(label: str) -> str | None:
    normalized = _normalized_label(label)
    return METADATA_LABELS.get(normalized)


def _extract_metadata(
    raw_extraction: dict,
    tables: list[dict],
    notes: list[str],
) -> dict[str, Any]:
    found: dict[str, Any] = {}
    candidates: dict[str, list[Any]] = {}

    def add(field: str, value: Any) -> None:
        value = str(value or "").strip()
        if value:
            candidates.setdefault(field, []).append(value)

    for table in tables:
        for row in _rows(table):
            for index in range(len(row) - 1):
                field = _label_field(row[index])
                if field:
                    add(field, row[index + 1])

    paragraphs = raw_extraction.get("paragraphs")
    if isinstance(paragraphs, list):
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                continue
            text = str(paragraph.get("text") or "")
            match = re.match(r"\s*([^:：]+)\s*[:：]\s*(.+?)\s*$", text)
            if match:
                field = _label_field(match.group(1))
                if field:
                    add(field, match.group(2))

    for field, values in candidates.items():
        normalized = {
            _date(value).isoformat() if field.endswith("_date") and _date(value)
            else value.strip().upper() if field == "currency"
            else value.strip().casefold()
            for value in values
        }
        if len(normalized) > 1:
            notes.append(f"Conflicting {field.replace('_', ' ')} values were found in Word tables.")
            continue
        value = values[0]
        if field.endswith("_date"):
            parsed_date = _date(value)
            if parsed_date is None:
                notes.append(f"The {field.replace('_', ' ')} value could not be read as a supported date.")
                continue
            found[field] = parsed_date
        elif field == "currency":
            found[field] = value.upper()
        else:
            found[field] = value
    return found


def _party_role(heading: str) -> str | None:
    normalized = _normalized_label(heading)
    if normalized.startswith((
        "supplier trn", "supplier tax", "supplier address", "supplier email",
        "buyer trn", "buyer tax", "buyer address", "buyer email",
        "vendor trn", "seller trn", "customer trn", "client trn",
    )):
        return None
    for role, labels in PARTY_LABELS.items():
        if any(
            normalized == label or normalized.startswith(f"{label} ")
            for label in labels
        ):
            return role
    return None


def _emirate(address: str) -> str | None:
    for emirate in EMIRATES:
        if re.search(rf"\b{re.escape(emirate)}\b", address, re.I):
            return emirate
    return None


def _extract_party_block(lines: list[str], role: str) -> dict[str, Any] | None:
    if not lines:
        return None
    heading_index = next(
        (index for index, line in enumerate(lines) if _party_role(line)),
        None,
    )
    if heading_index is None:
        return None

    values = lines[heading_index + 1:]
    name = None
    address_lines: list[str] = []
    trn = None
    email = None
    for line in values:
        trn_match = re.search(r"\bTRN\s*[:#-]?\s*([0-9 -]{8,24})", line, re.I)
        if trn_match:
            trn = re.sub(r"\D", "", trn_match.group(1))
            continue
        email_match = re.search(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            line,
            re.I,
        )
        if email_match:
            email = email_match.group(0)
            line = line[:email_match.start()] + line[email_match.end():]
            line = line.strip(" \t,;")
            if not line:
                continue
        if _normalized_label(line) in {"email", "email address", "e mail"}:
            continue
        if name is None:
            if re.match(r"^(supplier|buyer|vendor|seller|customer|client|email)\b", line, re.I):
                continue
            name = line.strip()
        else:
            address_lines.append(line.strip())

    address = ", ".join(part for part in address_lines if part) or None
    prefix = "supplier" if role == "supplier" else "customer"
    result = {
        f"{prefix}_name": name,
        f"{prefix}_address": address,
        f"{prefix}_emirate": _emirate(address or ""),
    }
    if role == "supplier":
        result["supplier_trn"] = trn
    else:
        result["customer_trn"] = trn
        result["customer_email"] = email
    return result


def _extract_parties(tables: list[dict], notes: list[str]) -> dict[str, Any]:
    parties: dict[str, Any] = {}
    for table in tables:
        rows = _rows(table)
        cells = table.get("cells")
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                lines = [line.strip() for line in value.splitlines() if line.strip()]
                role = next((_party_role(line) for line in lines if _party_role(line)), None)
                if role is None:
                    continue
                block_lines = list(lines)
                if len(block_lines) == 1:
                    for following in rows[row_index + 1:]:
                        if column_index >= len(following):
                            break
                        next_value = following[column_index]
                        if any(_party_role(line) for line in next_value.splitlines()):
                            break
                        block_lines.extend(
                            part.strip()
                            for part in next_value.splitlines()
                            if part.strip()
                        )
                party = _extract_party_block(block_lines, role)
                if party:
                    for field, field_value in party.items():
                        if field_value is None:
                            continue
                        if field in parties and str(parties[field]).casefold() != str(field_value).casefold():
                            notes.append(f"Conflicting {role} invoice details were found.")
                            parties.pop(field, None)
                        elif field not in parties:
                            parties[field] = field_value
        if isinstance(cells, list):
            for row in cells:
                if not isinstance(row, list):
                    continue
                for cell in row:
                    if not isinstance(cell, dict):
                        continue
                    for nested_number in cell.get("nested_tables", []):
                        nested = next(
                            (item for item in tables if item.get("table_number") == nested_number),
                            None,
                        )
                        if nested:
                            nested_party = _extract_parties([nested], notes)
                            for field, value in nested_party.items():
                                parties.setdefault(field, value)
    return parties


def _item_column(label: str) -> str | None:
    normalized = _normalized_label(label)
    if normalized in ITEM_LABELS:
        return ITEM_LABELS[normalized]
    if normalized.startswith("unit price "):
        return "unit_price_aed"
    if normalized.startswith("taxable "):
        return "taxable_value_aed"
    if normalized.startswith("vat ") and "%" not in normalized and "rate" not in normalized:
        return "vat_amount_aed"
    if normalized.startswith("line total "):
        return "line_total_aed"
    return None


def _extract_items(tables: list[dict], notes: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for table in tables:
        rows = _rows(table)
        header_index = None
        columns: dict[int, str] = {}
        for row_index, row in enumerate(rows):
            mapped = {
                column_index: field
                for column_index, label in enumerate(row)
                if (field := _item_column(label)) is not None
            }
            if "description" in mapped.values() and (
                "quantity" in mapped.values()
                or "unit_price_aed" in mapped.values()
                or "taxable_value_aed" in mapped.values()
            ):
                header_index = row_index
                columns = mapped
                break
        if header_index is None:
            continue

        table_number = table.get("table_number")
        for row_index, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            if len(row) <= max(columns, default=-1):
                continue
            description = row[next(
                index for index, field in columns.items() if field == "description"
            )].strip()
            if not description or _normalized_label(description) in SUMMARY_LABELS:
                continue
            item: dict[str, Any] = {
                "description": description,
                "source_table": table_number,
                "source_row": row_index,
            }
            for column_index, field in columns.items():
                if field == "description" or column_index >= len(row):
                    continue
                value = row[column_index].strip()
                if not value:
                    continue
                if field == "unit":
                    item[field] = value
                    continue
                precision = (
                    Decimal("0.001")
                    if field == "quantity"
                    else Decimal("0.01")
                )
                number = _decimal(value, precision)
                if number is None:
                    notes.append(
                        f"Unrecognized {field.replace('_', ' ')} in Word table "
                        f"{table_number}, row {row_index}."
                    )
                    continue
                item[field] = number
            result.append(item)
    return result


def _extract_summary(
    tables: list[dict],
    notes: list[str],
) -> dict[str, Any]:
    candidates: dict[str, list[Decimal]] = {}
    for table in tables:
        for row in _rows(table):
            if len(row) < 2:
                continue
            label = _normalized_label(row[0])
            field = SUMMARY_LABELS.get(label)
            if field is None and label.startswith("vat at "):
                field = "vat_amount_aed"
            if field is None:
                continue
            amount = _decimal(row[1])
            if amount is None:
                notes.append(f"The {label} amount in a Word summary table could not be read.")
                continue
            candidates.setdefault(field, []).append(amount)

    result: dict[str, Any] = {}
    for field, values in candidates.items():
        if len(set(values)) > 1:
            notes.append(f"Conflicting {field.replace('_', ' ')} amounts were found in Word tables.")
            continue
        result[field] = values[0]
    return result


def _financial_consistency(
    items: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[bool, list[str]]:
    if not items:
        return False, ["Line items were not identified."]
    warnings: list[str] = []
    complete = True
    gross = Decimal("0")
    taxable = Decimal("0")
    discount = Decimal("0")
    vat_total = Decimal("0")
    line_total = Decimal("0")
    for item in items:
        quantity = item.get("quantity")
        unit_price = item.get("unit_price_aed")
        item_discount = item.get("discount_aed", Decimal("0"))
        item_taxable = item.get("taxable_value_aed")
        rate = item.get("vat_rate")
        item_vat = item.get("vat_amount_aed")
        item_total = item.get("line_total_aed")
        if quantity is None or unit_price is None or item_taxable is None or rate is None or item_vat is None or item_total is None:
            complete = False
            continue
        expected_taxable = (quantity * unit_price - item_discount).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        expected_vat = (item_taxable * rate / Decimal("100")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        expected_total = item_taxable + item_vat
        if item_taxable != expected_taxable:
            warnings.append("A line item's taxable amount does not match quantity, price and discount.")
        if item_vat != expected_vat:
            warnings.append("A line item's VAT amount does not match its VAT rate.")
        if item_total != expected_total:
            warnings.append("A line item's total does not match taxable amount and VAT.")
        gross += quantity * unit_price
        taxable += item_taxable
        discount += item_discount
        vat_total += item_vat
        line_total += item_total

    if not complete:
        warnings.append("One or more line-item amounts are missing; financial consistency is unconfirmed.")
        return False, warnings

    for field, calculated in (
        ("subtotal_before_discount_aed", gross),
        ("subtotal_aed", taxable),
        ("discount_aed", discount),
        ("vat_amount_aed", vat_total),
        ("total_amount_aed", line_total),
    ):
        source = summary.get(field)
        if source is not None and source != calculated.quantize(CENT, rounding=ROUND_HALF_UP):
            warnings.append(
                f"The Word summary {field.replace('_', ' ')} does not match its line items."
            )
    return not warnings, warnings


def parse_docx_invoice(raw_extraction: dict) -> dict[str, Any]:
    """Parse Word table structures locally; never send document content to AI."""
    notes: list[str] = []
    raw_tables = raw_extraction.get("tables")
    tables = [
        table for table in raw_tables
        if isinstance(table, dict)
    ] if isinstance(raw_tables, list) else []
    fields = _extract_metadata(raw_extraction, tables, notes)
    fields.update(_extract_parties(tables, notes))
    items = _extract_items(tables, notes)
    summary = _extract_summary(tables, notes)
    fields.update(summary)
    fields["items"] = items
    fields["currency"] = str(fields.get("currency") or "").upper() or None
    fields["document_classification"] = "single_invoice"
    fields["source_filename"] = raw_extraction.get("filename")
    fields["source_table"] = next(
        (
            table.get("table_number")
            for table in tables
            if _extract_items([table], []) or _extract_summary([table], [])
        ),
        None,
    )
    title_text = " ".join(
        str(paragraph.get("text") or "")
        for paragraph in raw_extraction.get("paragraphs", [])
        if isinstance(paragraph, dict)
    )
    if re.search(r"\btax\s+invoice\b", title_text, re.I) or any(
        re.search(r"\btax\s+invoice\b", cell, re.I)
        for table in tables for row in _rows(table) for cell in row
    ):
        fields["invoice_type"] = "tax_invoice"

    consistent, consistency_notes = _financial_consistency(items, summary)
    notes.extend(consistency_notes)
    required_fields = (
        "invoice_number", "supplier_name", "supplier_trn",
        "customer_name", "customer_trn", "issue_date", "due_date",
        "currency", "subtotal_aed", "discount_aed", "vat_amount_aed",
        "total_amount_aed",
    )
    missing = [field for field in required_fields if fields.get(field) is None]
    if missing:
        notes.append(
            "Required Word invoice fields were not identified: "
            + ", ".join(field.replace("_", " ") for field in missing)
            + "."
        )
    if not fields.get("items"):
        notes.append("No invoice line-item table was confidently identified.")
    if fields.get("supply_date") is None:
        notes.append("Supply date was not identified in the Word tables.")
    if fields.get("place_of_supply") is None:
        notes.append("Place of supply was not identified in the Word tables.")
    fields["missing_fields"] = sorted(set(
        missing
        + (["items"] if not items else [])
        + (["supply_date"] if fields.get("supply_date") is None else [])
        + (["place_of_supply"] if fields.get("place_of_supply") is None else [])
    ))
    fields["extraction_notes"] = list(dict.fromkeys(notes))

    evidence = (
        bool(fields.get("invoice_number")),
        bool(fields.get("supplier_name")),
        bool(fields.get("customer_name")),
        bool(fields.get("supplier_trn")),
        bool(fields.get("customer_trn")),
        bool(fields.get("issue_date")),
        bool(fields.get("due_date")),
        bool(fields.get("currency")),
        bool(items) and all(
            item.get("quantity") is not None
            and item.get("unit_price_aed") is not None
            and item.get("taxable_value_aed") is not None
            and item.get("vat_rate") is not None
            and item.get("vat_amount_aed") is not None
            and item.get("line_total_aed") is not None
            for item in items
        ),
        bool(fields.get("total_amount_aed")),
        consistent,
    )
    fields["extraction_confidence"] = round(sum(evidence) / len(evidence), 2)

    validation_errors: list[dict[str, Any]] = []
    try:
        validated = UAEInvoiceExtractionSchema.model_validate(fields)
        invoices = [validated.model_dump(mode="json")]
    except ValidationError as exc:
        validation_errors = [
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "type": str(error.get("type", "validation_error")),
            }
            for error in exc.errors()
        ]
        locations = sorted({
            ".".join(error["loc"]) or "invoice"
            for error in validation_errors
        })
        notes.append(
            "Structured Word invoice values could not be validated for fields: "
            + ", ".join(locations)
            + ". Administrator review is required."
        )
        invoices = []

    required_review_fields = (
        "invoice_number", "supplier_name", "customer_name",
        "issue_date", "currency", "total_amount_aed",
    )
    ambiguous = any("conflicting " in note.casefold() for note in notes)
    manual_review = (
        bool(validation_errors)
        or any(fields.get(field) is None for field in required_review_fields)
        or not items
        or not consistent
        or ambiguous
    )
    return {
        "document_classification": "single_invoice" if invoices else "unknown",
        "invoices": invoices,
        "extraction_notes": list(dict.fromkeys(notes)),
        "processed_record_count": len(items),
        "processing_mode": "LOCAL_ONLY",
        "local_extraction_reliable": bool(invoices) and not manual_review,
        "manual_review_required": manual_review,
        "mapping_requests": {},
        "worksheet_classifications": {},
        "parser_version": "privacy-v3-docx",
        "docx_table_count": len(tables),
        "docx_validation_errors": validation_errors,
        "financially_consistent": consistent,
    }
