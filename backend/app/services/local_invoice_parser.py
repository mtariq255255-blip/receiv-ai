import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from pydantic import ValidationError

from app.schemas.uae_invoice import UAEInvoiceExtractionSchema
from app.services.invoice_column_mapper import map_columns
from app.services.docx_invoice_parser import parse_docx_invoice
from app.services.pdf_invoice_layout_parser import parse_pdf_layout
from app.services.privacy_filter import sanitize_column_headings


PARSER_VERSION = "privacy-v2"
MAX_LOCAL_RECORDS = 100_000
CENT = Decimal("0.01")


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        normalized = str(value).strip().replace(",", "")
        normalized = re.sub(r"^(AED|USD|EUR|GBP)\s*", "", normalized, flags=re.I)
        if normalized.startswith("(") and normalized.endswith(")"):
            normalized = f"-{normalized[1:-1]}"
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    result = decimal_or_none(value)
    return result if result is not None else Decimal("0")


def calculate_taxable_value(
    quantity: Any,
    unit_price: Any,
    discount: Any,
) -> Decimal | None:
    qty = decimal_or_none(quantity)
    price = decimal_or_none(unit_price)
    if qty is None or price is None:
        return None
    return ((qty * price) - decimal_or_zero(discount)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def calculate_vat(taxable_value: Any, vat_rate: Any) -> Decimal | None:
    taxable = decimal_or_none(taxable_value)
    rate = decimal_or_none(vat_rate)
    if taxable is None or rate is None:
        return None
    return (taxable * rate / Decimal("100")).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _worksheet_classification(mapping: dict) -> str:
    targets = set(mapping["resolved"])
    targets.update(mapping.get("ai_targets", []))
    if "invoice_number" not in targets:
        return "ignore"
    if "description" in targets:
        return "detail"
    if (
        "total_amount_aed" in targets
        or {"subtotal_aed", "vat_amount_aed"}.issubset(targets)
    ):
        return "summary"
    return "ambiguous"


def _local_mapping(columns: list[str], ai_mapping: dict[str, str]) -> dict:
    mapping = map_columns(columns)
    resolved = dict(mapping["resolved"])
    targets = set(resolved)
    for column, target in ai_mapping.items():
        if column not in columns or column not in mapping["unresolved"]:
            continue
        if target in targets:
            existing_column = resolved.pop(target, None)
            conflict_columns = mapping["conflicts"].setdefault(target, [])
            if existing_column is not None and existing_column not in conflict_columns:
                conflict_columns.append(existing_column)
            conflict_columns.append(column)
            continue
        resolved[target] = column
        targets.add(target)
    mapping["resolved"] = resolved
    mapping["ai_targets"] = list(ai_mapping.values())
    return mapping


def _source_value(row: dict, mapping: dict, target: str) -> Any:
    column = mapping["resolved"].get(target)
    return _clean(row.get(column)) if column is not None else None


def _identity_value(value: Any) -> str:
    return str(value or "").strip().casefold()


def _item_from_row(row: dict, mapping: dict, row_number: int, notes: list[str]) -> dict | None:
    description = _source_value(row, mapping, "description")
    if description is None:
        notes.append(f"Line item at source row {row_number} has no description.")
        return None

    item: dict[str, Any] = {"description": str(description)}
    for target in (
        "quantity", "unit", "unit_price_aed", "discount_aed",
        "taxable_value_aed", "vat_rate", "vat_amount_aed", "line_total_aed",
    ):
        value = _source_value(row, mapping, target)
        if value is None:
            continue
        if target == "unit":
            item[target] = str(value)
        elif target in {"quantity", "vat_rate"}:
            item[target] = decimal_or_none(value)
        else:
            item[target] = decimal_or_none(value)
        if item[target] is None:
            notes.append(f"Unparseable {target} value at source row {row_number}.")
            item.pop(target)
    item["source_row"] = row_number
    return item


def _sum_source_values(rows: list[dict], mapping: dict, field: str) -> Decimal | None:
    values = [
        decimal_or_none(_source_value(row, mapping, field))
        for row in rows
    ]
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)


def _one_source_value(rows: list[dict], mapping: dict, field: str) -> Any:
    values = [
        _source_value(row, mapping, field)
        for row in rows
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    first = values[0]
    if any(str(value).strip() != str(first).strip() for value in values[1:]):
        return first
    return first


def _group_fields(rows: list[dict], mapping: dict, notes: list[str]) -> dict:
    source_rows = [row for row, _row_number in rows]
    fields = {
        "invoice_number": _one_source_value(source_rows, mapping, "invoice_number"),
        "supplier_name": _one_source_value(source_rows, mapping, "supplier_name"),
        "supplier_trn": _one_source_value(source_rows, mapping, "supplier_trn"),
        "supplier_address": _one_source_value(source_rows, mapping, "supplier_address"),
        "supplier_emirate": _one_source_value(source_rows, mapping, "supplier_emirate"),
        "customer_name": _one_source_value(source_rows, mapping, "customer_name"),
        "customer_trn": _one_source_value(source_rows, mapping, "customer_trn"),
        "customer_address": _one_source_value(source_rows, mapping, "customer_address"),
        "customer_email": _one_source_value(source_rows, mapping, "customer_email"),
        "customer_emirate": _one_source_value(source_rows, mapping, "customer_emirate"),
        "issue_date": _one_source_value(source_rows, mapping, "issue_date"),
        "supply_date": _one_source_value(source_rows, mapping, "supply_date"),
        "due_date": _one_source_value(source_rows, mapping, "due_date"),
        "place_of_supply": _one_source_value(source_rows, mapping, "place_of_supply"),
        "currency": _one_source_value(source_rows, mapping, "currency"),
        "payment_status": _one_source_value(source_rows, mapping, "payment_status"),
    }

    # Conflicting header values are kept out of the invoice object and surfaced
    # as a manual-review condition rather than choosing an arbitrary row.
    for target, column in mapping["resolved"].items():
        if target in {"description", "quantity", "unit", "unit_price_aed",
                      "discount_aed", "taxable_value_aed", "vat_rate",
                      "vat_amount_aed", "line_total_aed"}:
            continue
        values = [_clean(row.get(column)) for row in source_rows]
        present = [value for value in values if value is not None]
        if present and any(str(value).strip() != str(present[0]).strip()
                           for value in present[1:]):
            notes.append(f"Conflicting {target} values within one invoice group.")
            fields[target] = None

    currency = str(fields["currency"] or "").upper()
    items = [
        item
        for row, row_number in rows
        if (item := _item_from_row(row, mapping, row_number, notes)) is not None
    ]
    fields["items"] = items

    if currency == "AED":
        source_subtotal = _one_source_value(source_rows, mapping, "subtotal_aed")
        fields["subtotal_aed"] = (
            decimal_or_none(source_subtotal)
            if source_subtotal is not None
            else _sum_source_values(source_rows, mapping, "taxable_value_aed")
        )
        fields["discount_aed"] = _sum_source_values(
            source_rows, mapping, "discount_aed"
        )
        fields["vat_amount_aed"] = _sum_source_values(
            source_rows, mapping, "vat_amount_aed"
        )
        source_total = _one_source_value(source_rows, mapping, "total_amount_aed")
        fields["total_amount_aed"] = (
            decimal_or_none(source_total)
            if source_total is not None
            else _sum_source_values(source_rows, mapping, "line_total_aed")
        )
    else:
        if any(_source_value(row, mapping, field) is not None
               for row in source_rows
               for field in ("subtotal_aed", "taxable_value_aed",
                             "vat_amount_aed", "total_amount_aed",
                             "line_total_aed", "unit_price_aed")):
            notes.append(
                "Monetary values were retained as source data but not treated as AED "
                "because the currency is not confirmed as AED."
            )
        fields.update({
            "subtotal_aed": None,
            "discount_aed": None,
            "vat_amount_aed": None,
            "total_amount_aed": None,
        })
        for item in fields["items"]:
            for amount in (
                "unit_price_aed", "discount_aed", "taxable_value_aed",
                "vat_amount_aed", "line_total_aed",
            ):
                item[amount] = None

    return fields


def _parse_text_invoice(raw_extraction: dict, notes: list[str]) -> list[dict]:
    text = raw_extraction.get("text")
    if not isinstance(text, str) or not text.strip():
        return []
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not re.fullmatch(r"---\s*Page\s+\d+\s*---", line.strip(), re.I)
    ]
    normalized_text = "\n".join(lines)
    found: dict[str, Any] = {}

    def capture(pattern: str, source: str = normalized_text) -> str | None:
        match = re.search(pattern, source, flags=re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else None

    invoice_number = capture(
        r"\binvoice\s*(?:number|no\.?|#)\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9/_-]*?)(?=TAX\s+INVOICE|\s|$)"
    )
    if invoice_number:
        found["invoice_number"] = invoice_number

    for field, pattern in (
        ("supplier_name", r"\b(?:supplier|vendor|seller)\s+name\s*[:\-]\s*([^\r\n]+)"),
        ("customer_name", r"\b(?:buyer|customer|client)\s+name\s*[:\-]\s*([^\r\n]+)"),
        ("supplier_trn", r"\b(?:supplier|vendor|seller)\s+trn\s*:\s*(\d{15})\b"),
        ("customer_trn", r"\b(?:buyer|customer|client)\s+trn\s*:\s*(\d{15})\b"),
    ):
        value = capture(pattern)
        if value:
            found[field] = value

    for field, pattern in (
        ("supplier_name", r"\b(?:supplier|vendor|seller)\s*(?:name)?\s*[:\-]\s*([^\r\n]+)"),
        ("customer_name", r"\b(?:buyer|customer|client)\s*(?:name)?\s*[:\-]\s*([^\r\n]+)"),
        ("issue_date", r"\b(?:invoice\s+date|issue\s+date)\s*[:\-]\s*([^\r\n]+)"),
        ("supply_date", r"\b(?:date\s+of\s+supply|supply\s+date)\s*[:\-]\s*([^\r\n]+)"),
        ("due_date", r"\b(?:due\s+date|payment\s+due)\s*[:\-]\s*([^\r\n]+)"),
    ):
        value = capture(pattern)
        if value:
            found[field] = value
    for field in ("issue_date", "supply_date", "due_date"):
        value = found.get(field)
        if isinstance(value, str):
            for date_format in (
                "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
                "%d %b %Y", "%d %B %Y",
            ):
                try:
                    found[field] = datetime.strptime(value, date_format).date()
                    break
                except ValueError:
                    continue

    currency_label = capture(r"\bcurrency\s*[:\-]\s*([A-Z]{3})\b")
    if currency_label:
        found["currency"] = currency_label.upper()

    for index, line in enumerate(lines):
        if re.search(r"\bSUPPLIER\b", line, re.I) and re.search(
            r"\bBILL\s+TO\b", line, re.I
        ):
            if index + 1 < len(lines):
                names = re.split(r"\s{2,}", lines[index + 1].strip())
                if len(names) >= 2:
                    found.setdefault("supplier_name", names[0].strip())
                    found.setdefault("customer_name", names[1].strip())
            if index + 2 < len(lines):
                addresses = re.split(r"\s{2,}", lines[index + 2].strip())
                if len(addresses) >= 2:
                    found.setdefault("supplier_address", addresses[0].strip())
                    found.setdefault("customer_address", addresses[1].strip())
            break

    date_pattern = re.compile(
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b"
    )
    for index, line in enumerate(lines):
        if (
            re.search(r"\binvoice\s+date\b", line, re.I)
            and re.search(r"\bsupply\s+date\b", line, re.I)
            and re.search(r"\bdue\s+date\b", line, re.I)
            and index + 1 < len(lines)
        ):
            dates = date_pattern.findall(lines[index + 1])
            if len(dates) >= 3:
                for field, value in zip(
                    ("issue_date", "supply_date", "due_date"),
                    dates[:3],
                ):
                    for date_format in ("%d %b %Y", "%d %B %Y"):
                        try:
                            found[field] = datetime.strptime(
                                value, date_format
                            ).date()
                            break
                        except ValueError:
                            continue
            currency_tokens = lines[index + 1].split()
            if currency_tokens and re.fullmatch(
                r"[A-Z]{3}", currency_tokens[-1], flags=re.I
            ):
                found["currency"] = currency_tokens[-1].upper()
            break

    found.setdefault(
        "currency",
        capture(r"\b(?:TOTAL\s+DUE|GRAND\s+TOTAL)\s*\(\s*([A-Z]{3})\s*\)"),
    )
    if found["currency"] is None and re.search(r"\bAED\b", normalized_text, re.I):
        found["currency"] = "AED"

    amount_pattern = r"([\d,]+(?:\.\d{1,2})?)\s*$"
    amounts: dict[str, Decimal] = {}
    for field, pattern in (
        ("total_amount_aed", rf"\b(?:total\s+due|grand\s+total|total\s+payable|invoice\s+total)\b(?:\s*\([^)]*\))?\s*[:\-]?\s*(?:AED\s*)?{amount_pattern}"),
        ("vat_amount_aed", rf"^\s*VAT(?:\s*\(\s*\d+(?:\.\d+)?%\s*\))?\s*(?:amount)?\s*[:\-]?\s*(?:AED\s*)?{amount_pattern}"),
        ("discount_aed", rf"^\s*Discount\s*[:\-]?\s*(?:AED\s*)?{amount_pattern}"),
        ("subtotal_aed", rf"^\s*Taxable\s+amount\s*[:\-]?\s*(?:AED\s*)?{amount_pattern}"),
    ):
        value = capture(pattern)
        amount = decimal_or_none(value) if value else None
        if amount is not None:
            amounts[field] = amount.quantize(CENT, rounding=ROUND_HALF_UP)

    item_pattern = re.compile(
        r"^\s*(?P<description>.+?)\s{2,}"
        r"(?P<quantity>\d+(?:\.\d+)?)\s+"
        r"(?P<unit_price>[\d,]+(?:\.\d{1,2})?)\s+"
        r"(?P<discount>[\d,]+(?:\.\d{1,2})?)\s+"
        r"(?P<vat_rate>\d+(?:\.\d+)?%)\s+"
        r"(?P<line_total>[\d,]+(?:\.\d{1,2})?)\s*$",
        re.I,
    )
    items: list[dict[str, Any]] = []
    for line in lines:
        match = item_pattern.match(line)
        if not match:
            continue
        values = match.groupdict()
        quantity = decimal_or_none(values["quantity"])
        unit_price = decimal_or_none(values["unit_price"])
        discount = decimal_or_none(values["discount"])
        vat_rate = decimal_or_none(values["vat_rate"].rstrip("%"))
        line_total = decimal_or_none(values["line_total"])
        if any(value is None for value in (
            quantity, unit_price, discount, vat_rate, line_total
        )):
            continue
        taxable = calculate_taxable_value(quantity, unit_price, discount)
        vat_amount = calculate_vat(taxable, vat_rate)
        if taxable is None or vat_amount is None:
            continue
        items.append({
            "description": values["description"].strip(),
            "quantity": quantity,
            "unit_price_aed": unit_price,
            "discount_aed": discount,
            "taxable_value_aed": taxable,
            "vat_rate": vat_rate,
            "vat_amount_aed": vat_amount,
            "line_total_aed": line_total,
        })

    if items:
        amounts["subtotal_aed"] = sum(
            (item["taxable_value_aed"] for item in items),
            Decimal("0"),
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        amounts["discount_aed"] = sum(
            (item["discount_aed"] for item in items),
            Decimal("0"),
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        amounts["vat_amount_aed"] = sum(
            (item["vat_amount_aed"] for item in items),
            Decimal("0"),
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        amounts.setdefault(
            "total_amount_aed",
            sum(
                (item["line_total_aed"] for item in items),
                Decimal("0"),
            ).quantize(CENT, rounding=ROUND_HALF_UP),
        )
    found.update(amounts)

    if not found or not re.search(r"\binvoice\b", normalized_text, re.I):
        return []
    found.setdefault("currency", None)
    found.update({
        "items": items,
        "extraction_confidence": 0.85 if items else 0.0,
        "missing_fields": [],
        "extraction_notes": [],
        "document_classification": "single_invoice",
        "source_filename": raw_extraction.get("filename"),
    })
    if not items:
        notes.append(
            "Text extraction found labeled invoice fields; line-item structure "
            "was not confidently identified."
        )
    else:
        notes.append(
            "Invoice fields and line items were parsed from labeled text; "
            "verify them against the retained source before approval."
        )
    return [found]


def parse_local_invoices(
    raw_extraction: dict,
    ai_mappings: dict[str, dict[str, str]] | None = None,
) -> dict:
    notes: list[str] = list(raw_extraction.get("warnings") or [])
    if raw_extraction.get("file_type") == "docx":
        docx_result = parse_docx_invoice(raw_extraction)
        if docx_result["invoices"]:
            return docx_result
        notes.extend(docx_result["extraction_notes"])

    pdf_layout_attempted = False
    pdf_layout_notes: list[str] = []
    pdf_layout_invoices: list[dict] = []
    if raw_extraction.get("file_type") == "pdf" and raw_extraction.get("layout_pages"):
        pdf_layout_attempted = True
        try:
            pdf_layout_invoices, pdf_layout_notes = parse_pdf_layout(raw_extraction)
        except ValidationError:
            pdf_layout_notes = [
                "Position-aware PDF extraction did not fit the supported invoice schema."
            ]
        if pdf_layout_invoices:
            notes.extend(pdf_layout_notes)

    tables = raw_extraction.get("tables")
    if not isinstance(tables, list):
        tables = []
    records = raw_extraction.get("records")
    if not isinstance(records, list):
        records = []
    if len(records) > MAX_LOCAL_RECORDS:
        notes.append(
            f"Local parser limit exceeded: processed at most {MAX_LOCAL_RECORDS} records."
        )
        records = records[:MAX_LOCAL_RECORDS]

    table_contexts: list[dict] = []
    mapping_requests: dict[str, dict[str, str]] = {}
    for table_index, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        rows = table.get("records")
        columns = table.get("columns")
        if not isinstance(columns, list):
            continue
        if not isinstance(rows, list):
            rows = records if table_index == 0 else None
        if not isinstance(rows, list):
            continue
        sheet_name = str(table.get("sheet_name") or f"Table {table_index + 1}")
        ai_mapping = (ai_mappings or {}).get(sheet_name, {})
        mapping = _local_mapping([str(column) for column in columns], ai_mapping)
        classification = _worksheet_classification(mapping)
        safe_headings = sanitize_column_headings(
            [column for column in mapping["unresolved"]]
        )
        if safe_headings:
            mapping_requests[sheet_name] = safe_headings
        table_contexts.append({
            "sheet_name": sheet_name,
            "rows": rows,
            "mapping": mapping,
            "classification": classification,
        })
        if mapping["conflicts"]:
            notes.append(
                f"Worksheet '{sheet_name}' has conflicting source columns; "
                "the affected fields require manual review."
            )

    detail_tables = [table for table in table_contexts
                     if table["classification"] == "detail"]
    summary_tables = [table for table in table_contexts
                      if table["classification"] == "summary"]
    selected_tables = detail_tables or summary_tables

    grouped: dict[tuple[str, str, str], list[tuple[dict, int]]] = defaultdict(list)
    group_mappings: dict[tuple[str, str, str], dict] = {}
    observed_suppliers: dict[tuple[str, str], set[str]] = defaultdict(set)
    supplier_buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    processed_count = 0

    for table in selected_tables:
        sheet_name = table["sheet_name"]
        mapping = table["mapping"]
        for row_index, row in enumerate(table["rows"], start=2):
            if not isinstance(row, dict):
                notes.append(
                    f"Non-record row in worksheet '{sheet_name}' at source row "
                    f"{row_index} was not parsed."
                )
                continue
            invoice_number = _source_value(row, mapping, "invoice_number")
            supplier_name = _source_value(row, mapping, "supplier_name")
            supplier_trn = _source_value(row, mapping, "supplier_trn")
            if invoice_number is None:
                notes.append(
                    f"Row {row_index} in worksheet '{sheet_name}' has no invoice "
                    "number and requires manual review."
                )
                group_token = f"__unassigned_row_{row_index}"
            else:
                group_token = str(invoice_number).strip().casefold()
            normalized_trn = (
                str(supplier_trn).replace(" ", "").replace("-", "").casefold()
                if supplier_trn else None
            )
            normalized_name = (
                _identity_value(supplier_name) if supplier_name else None
            )
            invoice_group = (sheet_name, group_token)
            buckets = supplier_buckets[invoice_group]
            matching_buckets = []
            if normalized_trn or normalized_name:
                for bucket in buckets:
                    bucket_trns = bucket["trns"]
                    bucket_names = bucket["names"]
                    if normalized_trn and bucket_trns:
                        matches = normalized_trn in bucket_trns
                    elif normalized_name and bucket_names:
                        matches = normalized_name in bucket_names
                    else:
                        matches = False
                    if matches:
                        matching_buckets.append(bucket)
            elif len(buckets) == 1:
                matching_buckets = buckets

            if len(matching_buckets) == 1:
                bucket = matching_buckets[0]
            else:
                bucket = {
                    "group_key": (
                        sheet_name,
                        group_token,
                        str(len(buckets)),
                    ),
                    "trns": set(),
                    "names": set(),
                }
                buckets.append(bucket)
            if normalized_trn:
                bucket["trns"].add(normalized_trn)
            if normalized_name:
                bucket["names"].add(normalized_name)

            supplier_identity = normalized_trn or normalized_name
            group_key = bucket["group_key"]
            grouped[group_key].append((row, row_index))
            group_mappings[group_key] = mapping
            if invoice_number is not None and supplier_identity:
                observed_suppliers[invoice_group].add(supplier_identity)
            processed_count += 1

    invoices: list[dict] = list(pdf_layout_invoices)
    for group_key, rows in grouped.items():
        sheet_name, invoice_key, _ = group_key
        mapping = group_mappings[group_key]
        invoice_notes: list[str] = []
        fields = _group_fields(rows, mapping, invoice_notes)
        fields["source_worksheet"] = sheet_name
        fields["source_row"] = rows[0][1]
        fields["source_filename"] = raw_extraction.get("filename")
        fields["document_classification"] = (
            "invoice_register" if detail_tables else "single_invoice"
        )
        if len(observed_suppliers.get((sheet_name, invoice_key), set())) > 1:
            invoice_notes.append(
                "The same invoice number is associated with conflicting supplier "
                "identities; review the separated records."
            )
        fields["extraction_notes"] = invoice_notes
        fields["extraction_confidence"] = (
            0.95 if not invoice_notes else 0.6
        )
        fields["missing_fields"] = [
            field
            for field in (
                "invoice_number", "supplier_name", "supplier_trn",
                "customer_name", "currency", "total_amount_aed",
            )
            if fields.get(field) is None
        ]
        try:
            invoice = UAEInvoiceExtractionSchema.model_validate(fields)
            invoices.append(invoice.model_dump(mode="json"))
        except ValidationError:
            notes.append(
                f"Invoice group from worksheet '{sheet_name}' contains values "
                "outside the supported invoice schema and requires manual review."
            )
            continue
        notes.extend(invoice_notes)

    if not invoices and not selected_tables and not pdf_layout_attempted:
        invoices = _parse_text_invoice(raw_extraction, notes)
        for data in invoices:
            try:
                parsed = UAEInvoiceExtractionSchema.model_validate(data)
                invoices = [parsed.model_dump(mode="json")]
            except ValidationError:
                invoices = []
                notes.append(
                    "Recognized invoice text did not fit the supported schema."
                )

    if pdf_layout_attempted and not pdf_layout_invoices:
        notes.extend(pdf_layout_notes)

    warning_text = " ".join(notes).casefold()
    truncated = any(
        marker in warning_text
        for marker in ("exceeds", "limit exceeded", "extra rows were omitted",
                       "extra columns were omitted", "could not read worksheet")
    )
    critical_missing = any(
        invoice.get(field) in (None, "")
        for invoice in invoices
        for field in (
            "invoice_number", "supplier_name", "supplier_trn",
            "currency", "total_amount_aed",
        )
    )
    conflicts = any("conflicting" in note.casefold() for note in notes)
    missing_line_items = any(not invoice.get("items") for invoice in invoices)
    local_reliable = bool(invoices) and not (
        critical_missing or conflicts or truncated or missing_line_items
    )
    if not invoices:
        notes.append(
            "No reviewable invoice was confidently identified; administrator "
            "review is required."
        )

    return {
        "document_classification": (
            "invoice_register" if detail_tables else
            "multiple_invoices" if len(invoices) > 1 else
            "single_invoice" if invoices else "unknown"
        ),
        "invoices": invoices,
        "extraction_notes": list(dict.fromkeys(notes)),
        "processed_record_count": processed_count,
        "processing_mode": "LOCAL_ONLY",
        "local_extraction_reliable": local_reliable,
        "manual_review_required": not local_reliable,
        "mapping_requests": mapping_requests,
        "worksheet_classifications": {
            table["sheet_name"]: table["classification"]
            for table in table_contexts
        },
        "parser_version": PARSER_VERSION,
    }
