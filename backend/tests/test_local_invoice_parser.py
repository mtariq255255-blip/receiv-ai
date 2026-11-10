from io import BytesIO
from decimal import Decimal

from openpyxl import Workbook

from app.agents.document_agent import document_agent
from app.services.file_detector import extract_uploaded_file
from app.services.local_invoice_parser import (
    calculate_taxable_value,
    calculate_vat,
    parse_local_invoices,
)


REGISTER_COLUMNS = [
    "Invoice Number", "Invoice Date", "Supply Date", "Due Date",
    "Supplier Name", "Supplier TRN", "Supplier Emirate", "Buyer Name",
    "Buyer TRN", "Buyer Emirate", "Currency", "Description", "Quantity",
    "Unit", "Unit Price", "Discount", "VAT Rate (%)", "Taxable Value",
    "VAT Amount", "Line Total", "Place of Supply", "Payment Status",
]


def sample_workbook() -> bytes:
    workbook = Workbook()
    register = workbook.active
    register.title = "Invoice Register"
    register.append(REGISTER_COLUMNS)
    invoices = [
        ("RAI-2026-1001", "Synthetic Supplier 1", "Consulting", 12000, 5),
        ("RAI-2026-1002", "Synthetic Supplier 2", "Office supplies", 4400, 5),
        ("RAI-2026-1003", "Synthetic Supplier 3", "Design", 3000, 5),
        ("RAI-2026-1003", "Synthetic Supplier 3", "Support", 1500, 5),
        ("RAI-2026-1004", "Synthetic Supplier 4", "Maintenance", 6200, 5),
        ("RAI-2026-1005", "Synthetic Supplier 5", "Training", 1800, 0),
        ("RAI-2026-1006", "Synthetic Supplier 6", "Delivery", 1050, 5),
    ]
    for number, supplier, description, taxable, rate in (
        invoices,
    ):
        supplier_number = int(number.rsplit("-", 1)[1]) - 1000
        vat = taxable * rate / 100
        register.append([
            number, "2026-10-01", "2026-10-01", "2026-11-01",
            supplier, f"1001234567{supplier_number:05d}", "Dubai",
            "Synthetic Buyer",
            "100987654300003", "Abu Dhabi", "AED", description, 1, "each",
            taxable, 0, rate, taxable, vat, taxable + vat, "Dubai", "Unpaid",
        ])

    summary = workbook.create_sheet("Invoice Summary")
    summary.append([
        "Invoice Number", "Supplier Name", "Buyer Name", "Invoice Date",
        "Due Date", "Currency", "Subtotal", "Discount", "VAT Amount",
        "Grand Total",
    ])
    for number in sorted({row[0] for row in invoices}):
        summary.append([number, "Synthetic Supplier", "Synthetic Buyer",
                        "2026-10-01", "2026-11-01", "AED", 1, 0, 0, 1])

    notes = workbook.create_sheet("Test Notes")
    notes.append(["Test Area", "What to verify"])
    notes.append(["VAT", "Synthetic test data"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_spreadsheet_register_is_grouped_and_summary_is_ignored(monkeypatch):
    extraction = extract_uploaded_file(sample_workbook(), "synthetic.xlsx")
    result = parse_local_invoices(extraction)

    assert extraction["metadata"]["worksheet_count"] == 3
    assert len(result["invoices"]) == 6
    assert result["processed_record_count"] == 7
    assert result["worksheet_classifications"] == {
        "Invoice Register": "detail",
        "Invoice Summary": "summary",
        "Test Notes": "ignore",
    }
    assert result["local_extraction_reliable"] is True

    target = next(
        invoice for invoice in result["invoices"]
        if invoice["invoice_number"] == "RAI-2026-1003"
    )
    assert len(target["items"]) == 2
    assert target["subtotal_aed"] == "4500.00"
    assert target["vat_amount_aed"] == "225.00"
    assert target["total_amount_aed"] == "4725.00"

    zero_vat = next(
        invoice for invoice in result["invoices"]
        if invoice["invoice_number"] == "RAI-2026-1005"
    )
    assert zero_vat["items"][0]["vat_rate"] == "0"
    assert zero_vat["vat_amount_aed"] == "0.00"

    def forbid_ai(*_args, **_kwargs):
        raise AssertionError("A familiar workbook must not call the AI gateway.")

    monkeypatch.setattr(
        "app.agents.document_agent.map_invoice_columns_with_ai",
        forbid_ai,
    )
    agent_result = document_agent.extract_document(extraction)
    assert agent_result["processing_mode"] == "LOCAL_ONLY"
    assert agent_result["ai_called"] is False
    assert len(agent_result["invoices"]) == 6


def test_financial_helpers_use_decimal_rounding():
    assert calculate_taxable_value("2", "10.005", "0") == Decimal("20.01")
    assert calculate_taxable_value("2", "10.00", "1.25") == Decimal("18.75")
    assert calculate_vat("4500", "5") == Decimal("225.00")
    assert calculate_vat("1800", "0") == Decimal("0.00")


def test_rows_with_missing_supplier_identity_join_only_unambiguous_invoice():
    extraction = {
        "filename": "synthetic.xlsx",
        "warnings": [],
        "records": [],
        "tables": [{
            "sheet_name": "Register",
            "columns": REGISTER_COLUMNS,
            "records": [
                [
                    "RAI-2026-2001", "2026-10-01", "2026-10-01",
                    "2026-11-01", "Synthetic Supplier", "100123456700003",
                    "Dubai", "Synthetic Buyer", "100987654300003",
                    "Abu Dhabi", "AED", "Consulting", 1, "hour", 100, 0,
                    5, 100, 5, 105, "Dubai", "Unpaid",
                ],
                [
                    "RAI-2026-2001", "2026-10-01", "2026-10-01",
                    "2026-11-01", None, None, "Dubai", "Synthetic Buyer",
                    "100987654300003", "Abu Dhabi", "AED", "Support", 1,
                    "hour", 50, 0, 5, 50, 2.5, 52.5, "Dubai", "Unpaid",
                ],
            ],
        }],
    }
    extraction["tables"][0]["records"] = [
        dict(zip(REGISTER_COLUMNS, row))
        for row in extraction["tables"][0]["records"]
    ]

    result = parse_local_invoices(extraction)

    assert len(result["invoices"]) == 1
    assert result["invoices"][0]["supplier_trn"] == "100123456700003"
    assert len(result["invoices"][0]["items"]) == 2
    assert result["local_extraction_reliable"] is True


def test_same_invoice_number_with_conflicting_supplier_ids_stays_separate():
    extraction = {
        "filename": "synthetic.xlsx",
        "warnings": [],
        "records": [],
        "tables": [{
            "sheet_name": "Register",
            "columns": REGISTER_COLUMNS,
            "records": [],
        }],
    }
    for supplier, trn, description in (
        ("Supplier A", "100123456700003", "First service"),
        ("Supplier B", "100123456700004", "Second service"),
    ):
        extraction["tables"][0]["records"].append(dict(zip(
            REGISTER_COLUMNS,
            [
                "RAI-2026-2002", "2026-10-01", "2026-10-01",
                "2026-11-01", supplier, trn, "Dubai", "Synthetic Buyer",
                "100987654300003", "Abu Dhabi", "AED", description, 1,
                "hour", 100, 0, 5, 100, 5, 105, "Dubai", "Unpaid",
            ],
        )))

    result = parse_local_invoices(extraction)

    assert len(result["invoices"]) == 2
    assert result["local_extraction_reliable"] is False
    assert all(
        "conflicting supplier identities" in " ".join(
            invoice["extraction_notes"]
        )
        for invoice in result["invoices"]
    )


def test_unstructured_uncertain_invoice_is_local_and_manual():
    result = document_agent.extract_document({
        "filename": "confidential.pdf",
        "file_type": "pdf",
        "text": (
            "Invoice Number: RAI-PRIVATE-1\n"
            "Supplier Name: Private Supplier\n"
            "Supplier TRN: 100123456700003"
        ),
        "records": [],
        "tables": [],
        "metadata": {},
        "warnings": [],
    })
    assert result["processing_mode"] == "MANUAL_REVIEW_REQUIRED"
    assert result["ai_called"] is False
    assert result["manual_review_required"] is True
