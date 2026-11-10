import re


COLUMN_ALIASES = {
    "invoice_number": [
        "invoice number", "invoice no", "invoice #", "tax invoice number",
        "invoice ref", "invoice reference", "invoice id",
    ],
    "supplier_name": ["supplier name", "vendor name", "seller name"],
    "supplier_trn": ["supplier trn", "vendor trn", "seller trn"],
    "supplier_address": ["supplier address", "vendor address", "seller address"],
    "supplier_emirate": ["supplier emirate", "vendor emirate"],
    "customer_name": ["buyer name", "customer name", "client name"],
    "customer_trn": ["buyer trn", "customer trn", "client trn"],
    "customer_address": ["buyer address", "customer address", "client address"],
    "customer_email": ["buyer email", "customer email", "client email"],
    "customer_emirate": ["buyer emirate", "customer emirate"],
    "issue_date": ["invoice date", "issue date", "date issued"],
    "supply_date": ["supply date", "date of supply"],
    "due_date": ["due date", "payment due date"],
    "currency": ["currency", "currency code"],
    "description": [
        "description", "item description", "service description", "product",
        "service",
    ],
    "quantity": ["quantity", "qty"],
    "unit": ["unit", "unit of measure"],
    "unit_price_aed": ["unit price", "price per unit", "rate"],
    "discount_aed": ["discount", "discount amount", "line discount"],
    "subtotal_aed": ["subtotal", "sub total", "taxable subtotal"],
    "taxable_value_aed": ["taxable value", "taxable amount"],
    "vat_rate": ["vat rate", "vat rate %", "vat rate (%)", "tax rate"],
    "vat_amount_aed": ["vat amount", "vat", "tax amount"],
    "line_total_aed": ["line total", "item total"],
    "total_amount_aed": [
        "grand total", "total payable", "invoice total", "amount aed",
        "invoice amount aed", "total aed",
    ],
    "place_of_supply": ["place of supply"],
    "payment_status": ["payment status", "status"],
}


def normalize_column(value: str) -> str:
    result = str(value).lower().strip()
    result = re.sub(r"[_-]+", " ", result)
    result = re.sub(r"\s+", " ", result)
    return result


def map_columns(columns: list[str]) -> dict:
    aliases: dict[str, set[str]] = {}
    for target, options in COLUMN_ALIASES.items():
        for option in options:
            aliases.setdefault(normalize_column(option), set()).add(target)

    candidates: dict[str, list[str]] = {}
    unresolved: list[str] = []
    ambiguous: list[str] = []
    for source_column in columns:
        targets = aliases.get(normalize_column(source_column), set())
        if len(targets) == 1:
            target = next(iter(targets))
            candidates.setdefault(target, []).append(source_column)
        elif len(targets) > 1:
            ambiguous.append(source_column)
        else:
            unresolved.append(source_column)

    conflicts = {
        target: source_columns
        for target, source_columns in candidates.items()
        if len(source_columns) > 1
    }
    resolved = {
        target: source_columns[0]
        for target, source_columns in candidates.items()
        if len(source_columns) == 1
    }
    for columns_for_target in conflicts.values():
        ambiguous.extend(columns_for_target)

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "ambiguous": list(dict.fromkeys(ambiguous)),
        "conflicts": conflicts,
    }
