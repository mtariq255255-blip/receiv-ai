"""Conservative, local-only parser for position-aware, text-based UAE invoices.

Returns invoice dictionaries matching UAEInvoiceExtractionSchema. Unmatched
layouts must go to manual review, never automatically to unredacted AI.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.uae_invoice import UAEInvoiceExtractionSchema

AMOUNT_RE = re.compile(r"^\s*(?:AED\s*)?\d[\d,]*(?:\.\d{1,2})?\s*$", re.I)
DATE_RE = re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
TRN_RE = re.compile(r"\b\d{15}\b")


def _amount(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"^AED\s*", "", str(value).strip(), flags=re.I).replace(",", "")
    try:
        return Decimal(cleaned) if AMOUNT_RE.fullmatch(str(value)) else None
    except InvalidOperation:
        return None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    match = DATE_RE.search(value)
    if not match:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(match.group(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def _lines(page: dict) -> list[dict]:
    lines = []
    for line in page.get("lines") or []:
        if not isinstance(line, dict) or not line.get("text"):
            continue
        bbox = line.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        lines.append({"text": str(line["text"]).strip(), "x": float(bbox[0]),
                      "y": float(bbox[1]), "x2": float(bbox[2]), "y2": float(bbox[3])})
    return sorted(lines, key=lambda r: (r["y"], r["x"]))


def _below(lines: list[dict], label: str, *, max_dy: float = 34) -> str | None:
    candidates = [r for r in lines if _normalize(r["text"]) == _normalize(label)]
    for anchor in candidates:
        options = [r for r in lines if 1 <= r["y"] - anchor["y"] <= max_dy
                   and abs(r["x"] - anchor["x"]) <= 38]
        if options:
            return min(options, key=lambda r: (r["y"] - anchor["y"], abs(r["x"] - anchor["x"])))['text']
    return None


def _section(lines: list[dict], header: str, x_right: float) -> dict[str, str | None]:
    anchors = [r for r in lines if _normalize(r["text"]) == _normalize(header)]
    if not anchors:
        return {"name": None, "address": None, "trn": None, "email": None}
    anchor = anchors[0]
    # Limit to same column and the supplier/buyer block directly below the title.
    candidates = [r for r in lines if anchor["y"] + 7 <= r["y"] <= anchor["y"] + 90
                  and anchor["x"] - 8 <= r["x"] < x_right]
    candidates.sort(key=lambda r: r["y"])
    regular = [r["text"] for r in candidates if not re.search(r"\bTRN\b|@", r["text"], re.I)]
    trns = [TRN_RE.search(r["text"]).group() for r in candidates if TRN_RE.search(r["text"])]
    emails = [r["text"] for r in candidates if re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", r["text"])]
    return {"name": regular[0] if regular else None,
            "address": regular[1] if len(regular) > 1 else None,
            "trn": trns[0] if trns else None,
            "email": emails[0] if emails else None}


def _row_cells(lines: list[dict], headers: list[dict], row_y: float) -> dict[str, str]:
    positions = [r["x"] for r in headers]
    names = [r["text"].casefold() for r in headers]
    ranges = []
    for i, pos in enumerate(positions):
        left = (positions[i - 1] + pos) / 2 if i else -1
        right = (pos + positions[i + 1]) / 2 if i + 1 < len(positions) else 10000
        ranges.append((left, right))
    result = {}
    for line in lines:
        if abs(line['y'] - row_y) > 6:
            continue
        x_center = (line['x'] + line['x2']) / 2
        # Numeric cells often right-align slightly *before* the next header,
        # so header starts are more robust than center-of-column boundaries.
        idx = min(range(len(positions)), key=lambda k: abs(line['x'] - positions[k]))
        result[names[idx]] = (result.get(names[idx], '') + ' ' + line['text']).strip()
    return result


def _items(lines: list[dict], notes: list[str]) -> list[dict]:
    aliases = {'description': ['description'], 'qty': ['qty', 'quantity'],
               'unit price': ['unit price', 'rate'], 'discount': ['discount'],
               'vat': ['vat', 'vat %'], 'line total': ['line total', 'amount']}
    headers = []
    for target, names in aliases.items():
        candidates = [r for r in lines if _normalize(r['text']) in names]
        if candidates:
            headers.append((target, candidates[0]))
    if len(headers) != 6:
        notes.append('PDF line-item table headers could not be identified reliably.')
        return []
    headers.sort(key=lambda p: p[1]['x'])
    if [key for key, _ in headers] != ['description', 'qty', 'unit price', 'discount', 'vat', 'line total']:
        notes.append('PDF line-item columns are in an unexpected order.')
        return []
    header_y = max(r['y'] for _, r in headers)
    # Only collect lines below the table heading and above the totals section.
    end_candidates = [r['y'] for r in lines if r['y'] > header_y + 15 and
                      _normalize(r['text']).startswith(('subtotal', 'total due', 'grand total'))]
    if not end_candidates:
        notes.append('PDF line-item table end was not identified.')
        return []
    end_y = min(end_candidates)
    body = [r for r in lines if header_y + 10 < r['y'] < end_y - 5]
    description_x = headers[0][1]['x']
    # Use the description cells as row anchors; avoid inventing items from unpaired text.
    anchors = [r for r in body if abs(r['x'] - description_x) < 24 and
               not AMOUNT_RE.fullmatch(r['text'])]
    items = []
    for anchor in anchors:
        row = [r for r in body if abs(r['y'] - anchor['y']) <= 6]
        # For this invoice family the six visible cells are aligned left-to-right.
        # Right-aligned numeric text does not share the header's starting x,
        # so positional proximity to header text would misclassify the total.
        ordered_cells = sorted(row, key=lambda entry: entry['x'])
        if len(ordered_cells) != len(headers):
            notes.append('A PDF item row does not contain six distinct columns.')
            continue
        cols = {name: entry['text'] for (name, _), entry in zip(headers, ordered_cells)}
        qty = _amount(cols['qty'])
        price = _amount(cols['unit price'])
        discount = _amount(cols['discount'])
        vat_string = (cols['vat'] or '').strip()
        vat_rate = _amount(vat_string.rstrip('%')) if vat_string.endswith('%') else None
        line_total = _amount(cols['line total'])
        if None in (qty, price, discount, vat_rate, line_total):
            notes.append('An invoice item contains ambiguous or missing numeric cells.')
            continue
        taxable = qty * price - discount
        vat = (taxable * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
        expected_total = taxable + vat
        if abs(expected_total - line_total) > Decimal('0.02'):
            notes.append('A PDF item line total disagrees with the calculated amount.')
        items.append({'description': cols['description'], 'quantity': qty,
                      'unit_price_aed': price, 'discount_aed': discount,
                      'taxable_value_aed': taxable, 'vat_rate': vat_rate,
                      'vat_amount_aed': vat, 'line_total_aed': line_total})
    return items


def _total(lines: list[dict], labels: tuple[str, ...]) -> Decimal | None:
    for anchor in lines:
        name = _normalize(anchor['text'])
        if not any(name == label or name.startswith(label + ' ') for label in labels):
            continue
        options = [r for r in lines if abs(r['y'] - anchor['y']) <= 5
                   and r['x'] > anchor['x2'] + 8 and _amount(r['text']) is not None]
        if options:
            return _amount(max(options, key=lambda r: r['x'])['text'])
    return None


def parse_pdf_layout(raw_extraction: dict[str, Any]) -> tuple[list[dict], list[str]]:
    """Parse known PDF layouts locally; return incomplete invoice for manual review."""
    notes: list[str] = []
    pages = raw_extraction.get('layout_pages') or []
    if not pages:
        return [], ['No PDF layout coordinates are available.']
    # Conservative v1: never combine different invoices across PDF pages.
    if len(pages) != 1:
        return [], ['Multi-page PDF layout requires manual review.']
    lines = _lines(pages[0])
    if not lines:
        return [], ['No positioned PDF text lines are available.']
    width = float(pages[0].get('width') or 595)
    supplier = _section(lines, 'SUPPLIER', width / 2)
    buyer = _section(lines, 'BILL TO', width)
    invoice_number = _below(lines, 'INVOICE NO.')
    if invoice_number and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_-]{1,99}', invoice_number):
        invoice_number = None
    currency = _below(lines, 'Currency')
    if not currency:
        for line in lines:
            if 'TOTAL DUE (AED)' in line['text'].upper():
                currency = 'AED'
                break
    issue_date = _date(_below(lines, 'Invoice date') or _below(lines, 'ISSUED'))
    supply_date = _date(_below(lines, 'Supply date'))
    due_date = _date(_below(lines, 'Due date'))
    items = _items(lines, notes)
    subtotal = _total(lines, ('taxable amount', 'subtotal before discount', 'subtotal'))
    discount = _total(lines, ('discount',))
    vat = _total(lines, ('vat (5%)', 'vat amount', 'total vat'))
    total = _total(lines, ('total due (aed)', 'grand total', 'total payable'))
    if items:
        # Invoice totals use net taxable value; line discounts are already
        # reflected in each item's taxable amount.
        subtotal = sum(
            (Decimal(str(item['taxable_value_aed'])) for item in items),
            Decimal('0'),
        )
        discount = sum(
            (Decimal(str(item['discount_aed'])) for item in items),
            Decimal('0'),
        )
        vat = sum(
            (Decimal(str(item['vat_amount_aed'])) for item in items),
            Decimal('0'),
        )
    if not currency or currency.upper() != 'AED':
        notes.append('Invoice currency was not reliably established as AED.')
        subtotal = discount = vat = total = None
    place = None
    for row in lines:
        m = re.search(r'Place of supply\s*:\s*([^.;]+)', row['text'], re.I)
        if m:
            place = m.group(1).strip()
            break
    fields = {'invoice_number': invoice_number,
              'supplier_name': supplier['name'], 'supplier_address': supplier['address'],
              'supplier_trn': supplier['trn'], 'customer_name': buyer['name'],
              'customer_address': buyer['address'], 'customer_email': buyer['email'],
              'customer_trn': buyer['trn'], 'issue_date': issue_date,
              'supply_date': supply_date, 'due_date': due_date,
              'currency': currency, 'place_of_supply': place, 'items': items,
              'subtotal_aed': subtotal, 'discount_aed': discount,
              'vat_amount_aed': vat, 'total_amount_aed': total,
              'document_classification': 'single_invoice',
              'source_filename': raw_extraction.get('filename'), 'source_page': 1}
    required = ('invoice_number', 'supplier_name', 'customer_name', 'issue_date',
                'currency', 'total_amount_aed')
    missing = [name for name in required if fields.get(name) is None]
    if not items:
        missing.append('items')
    fields['missing_fields'] = missing
    fields['extraction_notes'] = notes
    fields['extraction_confidence'] = round(max(0, 1 - len(missing) / 7), 2)
    if missing:
        notes.append('Local PDF extraction incomplete; administrator review is required.')
    parsed = UAEInvoiceExtractionSchema.model_validate(fields)
    return [parsed.model_dump(mode='json')], notes
