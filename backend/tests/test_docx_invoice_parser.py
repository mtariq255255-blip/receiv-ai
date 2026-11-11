from io import BytesIO

from docx import Document

from app.agents.document_agent import document_agent
from app.services.file_detector import extract_uploaded_file
from app.services.local_invoice_parser import parse_local_invoices


def sample_docx() -> bytes:
    document = Document()
    document.add_paragraph("TAX INVOICE")

    metadata = document.add_table(rows=3, cols=4)
    for row, values in zip(metadata.rows, (
        ("Invoice No.", "RAI-WD-2026-2101", "Issue Date", "11 Nov 2026"),
        ("Due Date", "11 Dec 2026", "Supply Date", "11 Nov 2026"),
        ("Currency", "AED", "Place of Supply", "Dubai, UAE"),
    )):
        for cell, value in zip(row.cells, values):
            cell.text = value

    parties = document.add_table(rows=5, cols=2)
    party_values = (
        ("SUPPLIER (FROM)", "BILL TO"),
        ("Harborline Technology Services LLC", "Cedar Point Facilities Management LLC"),
        ("Business Bay, Dubai, United Arab Emirates", "Al Nahda, Sharjah, United Arab Emirates"),
        ("Supplier TRN: 100111222300003", "Buyer TRN: 100777888900003"),
        ("Email:", "accounts@cedarpoint-example.test"),
    )
    for row, values in zip(parties.rows, party_values):
        for cell, value in zip(row.cells, values):
            cell.text = value

    items = document.add_table(rows=3, cols=9)
    item_values = (
        (
            "Description", "Quantity", "Unit", "Unit Price (AED)",
            "Discount (AED)", "Taxable (AED)", "VAT Rate (%)",
            "VAT (AED)", "Line Total (AED)",
        ),
        (
            "IT infrastructure assessment", "2", "Day", "1200.00",
            "100.00", "2300.00", "5%", "115.00", "2415.00",
        ),
        (
            "Cloud backup configuration", "1", "Service", "850.00",
            "0.00", "850.00", "5%", "42.50", "892.50",
        ),
    )
    for row, values in zip(items.rows, item_values):
        for cell, value in zip(row.cells, values):
            cell.text = value

    summary = document.add_table(rows=5, cols=2)
    summary_values = (
        ("Subtotal before discount", "3,250.00"),
        ("Discount", "100.00"),
        ("Taxable Amount", "3,150.00"),
        ("VAT at 5%", "157.50"),
        ("Grand Total", "3,307.50"),
    )
    for row, values in zip(summary.rows, summary_values):
        for cell, value in zip(row.cells, values):
            cell.text = value

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def extract_sample() -> dict:
    return extract_uploaded_file(sample_docx(), "sample-invoice.docx")


def test_docx_invoice_is_structured_and_financially_consistent():
    extraction = extract_sample()
    result = parse_local_invoices(extraction)

    assert len(extraction["tables"]) == 4
    assert len(result["invoices"]) == 1
    assert result["local_extraction_reliable"] is True
    assert result["mapping_requests"] == {}
    invoice = result["invoices"][0]
    assert invoice["invoice_number"] == "RAI-WD-2026-2101"
    assert invoice["supplier_name"] == "Harborline Technology Services LLC"
    assert invoice["supplier_trn"] == "100111222300003"
    assert invoice["customer_name"] == "Cedar Point Facilities Management LLC"
    assert invoice["customer_trn"] == "100777888900003"
    assert invoice["issue_date"] == "2026-11-11"
    assert invoice["due_date"] == "2026-12-11"
    assert invoice["currency"] == "AED"
    assert invoice["subtotal_before_discount_aed"] == "3250.00"
    assert invoice["subtotal_aed"] == "3150.00"
    assert invoice["discount_aed"] == "100.00"
    assert invoice["vat_amount_aed"] == "157.50"
    assert invoice["total_amount_aed"] == "3307.50"
    assert len(invoice["items"]) == 2
    assert invoice["items"][0]["quantity"] == "2.000"
    assert invoice["items"][0]["taxable_value_aed"] == "2300.00"
    assert invoice["items"][1]["line_total_aed"] == "892.50"
    assert invoice["supplier_address"] == "Business Bay, Dubai, United Arab Emirates"


def test_conflicting_docx_totals_require_review():
    extraction = extract_sample()
    extraction["tables"][-1]["rows"].append(["Grand Total", "999.00"])

    result = parse_local_invoices(extraction)

    assert len(result["invoices"]) == 1
    assert result["local_extraction_reliable"] is False
    assert result["manual_review_required"] is True
    assert any("conflicting total amount" in note.casefold()
               for note in result["extraction_notes"])


def test_docx_extraction_preserves_paragraphs_and_never_calls_ai(monkeypatch):
    extraction = extract_sample()
    _, normalized = document_agent._serialize_input(extraction)
    assert normalized["paragraphs"] == extraction["paragraphs"]

    def forbid_ai(*_args, **_kwargs):
        raise AssertionError("DOCX invoice content must not be sent to AI.")

    monkeypatch.setattr(
        "app.agents.document_agent.map_invoice_columns_with_ai",
        forbid_ai,
    )
    monkeypatch.setattr(
        "app.agents.document_agent.settings.ai_fallback_enabled",
        True,
    )
    result = document_agent.extract_document(extraction)

    assert result["ai_called"] is False
    assert result["sensitive_data_transmitted"] is False
    assert result["docx_table_count"] == 4
    assert result["financially_consistent"] is True
    assert result["invoices"][0]["invoice_number"] == "RAI-WD-2026-2101"


def test_docx_without_line_item_table_is_not_marked_reliable():
    extraction = extract_sample()
    extraction["tables"].pop(2)

    result = parse_local_invoices(extraction)

    assert len(result["invoices"]) == 1
    assert result["invoices"][0]["items"] == []
    assert result["local_extraction_reliable"] is False
    assert result["manual_review_required"] is True
