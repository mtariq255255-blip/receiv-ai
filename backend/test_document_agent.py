from unittest.mock import patch

from pydantic import ValidationError

from app.agents.document_agent import DocumentIntelligenceAgent
from app.schemas.uae_invoice import UAEInvoiceItemSchema


def run_tests() -> None:
    agent = DocumentIntelligenceAgent()

    text_invoice = {
        "filename": "synthetic.pdf",
        "file_type": "pdf",
        "text": (
            "Invoice Number: RAI-TEST-1\n"
            "Supplier Name: Test Supplier\n"
            "Supplier TRN: 100123456700003\n"
            "Currency: AED\n"
            "Grand Total: AED 262.50"
        ),
        "records": [],
        "tables": [],
        "metadata": {},
        "warnings": [],
    }
    with patch(
        "app.agents.document_agent.map_invoice_columns_with_ai",
        side_effect=AssertionError("Unstructured text must stay local."),
    ):
        result = agent.extract_document(text_invoice)
    invoice = result["invoices"][0]
    assert invoice["invoice_number"] == "RAI-TEST-1"
    assert invoice["supplier_trn"] == "100123456700003"
    assert invoice["customer_trn"] is None
    assert result["ai_called"] is False
    assert result["sensitive_data_transmitted"] is False
    assert result["manual_review_required"] is True
    print("PASS: unstructured text stays local and requires review")

    columns = [
        "Invoice Number", "Supplier Name", "Supplier TRN", "Buyer Name",
        "Currency", "Description", "Quantity", "Unit Price", "VAT Rate (%)",
        "Taxable Value", "VAT Amount", "Line Total",
    ]
    records = [
        {
            "Invoice Number": "RAI-TEST-2",
            "Supplier Name": "Test Supplier",
            "Supplier TRN": "100123456700003",
            "Buyer Name": "Test Buyer",
            "Currency": "AED",
            "Description": description,
            "Quantity": "1",
            "Unit Price": taxable,
            "VAT Rate (%)": "5",
            "Taxable Value": taxable,
            "VAT Amount": vat,
            "Line Total": total,
        }
        for description, taxable, vat, total in (
            ("Consulting", "200.00", "10.00", "210.00"),
            ("Support", "50.00", "2.50", "52.50"),
        )
    ]
    workbook = {
        "filename": "synthetic.xlsx",
        "file_type": "xlsx",
        "text": "",
        "records": [],
        "tables": [{
            "sheet_name": "Register",
            "columns": columns,
            "records": records,
        }],
        "metadata": {},
        "warnings": [],
    }
    with patch(
        "app.agents.document_agent.map_invoice_columns_with_ai",
        side_effect=AssertionError("Known headings must be parsed locally."),
    ):
        result = agent.extract_document(workbook)
    invoice = result["invoices"][0]
    assert invoice["invoice_number"] == "RAI-TEST-2"
    assert len(invoice["items"]) == 2
    assert invoice["subtotal_aed"] == "250.00"
    assert invoice["vat_amount_aed"] == "12.50"
    assert invoice["total_amount_aed"] == "262.50"
    assert result["processing_mode"] == "LOCAL_ONLY"
    assert result["ai_called"] is False
    assert result["manual_review_required"] is False
    print("PASS: known spreadsheet headings and totals parse locally")

    incomplete = {
        **workbook,
        "tables": [{
            **workbook["tables"][0],
            "records": [{
                **records[0],
                "Supplier TRN": None,
            }],
        }],
    }
    result = agent.extract_document(incomplete)
    assert result["processing_mode"] == "MANUAL_REVIEW_REQUIRED"
    assert result["ai_called"] is False
    print("PASS: missing supplier identity requires administrator review")

    try:
        UAEInvoiceItemSchema(description="")
    except ValidationError:
        pass
    else:
        raise AssertionError("Invalid line item should be rejected.")
    print("PASS: invalid structured values are rejected")

    print("All document agent tests passed (no OpenAI request).")


if __name__ == "__main__":
    run_tests()
