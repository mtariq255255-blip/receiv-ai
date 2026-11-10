from io import BytesIO
from unittest.mock import patch

import pymupdf
from docx import Document
from openpyxl import Workbook

from app.services.file_detector import extract_uploaded_file
from app.services.csv_extractor import extract_csv, extract_csv_rows


def make_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Invoice Number RAI-TEST-1001")
    data = document.tobytes()
    document.close()
    return data


def make_docx() -> bytes:
    document = Document()
    document.add_paragraph("Invoice Number RAI-TEST-1002")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Description"
    table.cell(0, 1).text = "Amount"
    table.cell(1, 0).text = "Consulting"
    table.cell(1, 1).text = "250.00"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def make_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(["Invoice Number", "Customer", "Amount", "Currency"])
    sheet.append(["RAI-TEST-1003", "Customer A", 100, "AED"])
    second_sheet = workbook.create_sheet("Other Invoices")
    second_sheet.append(["Invoice Number", "Customer", "Amount", "Currency"])
    second_sheet.append(["RAI-TEST-1004", "Customer B", 200, "AED"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def make_csv() -> bytes:
    return (
        b"invoice_number,customer_name,amount,currency\n"
        b"RAI-TEST-1005,Customer A,100,AED\n"
        b"RAI-TEST-1006,Customer B,200,AED\n"
    )


def expect_value_error(file_bytes: bytes, filename: str) -> None:
    try:
        extract_uploaded_file(file_bytes, filename)
    except ValueError:
        return
    raise AssertionError(f"{filename} should have been rejected.")


def run_tests() -> None:
    print("RECEIVAI EXTRACTION TEST")

    pdf = extract_uploaded_file(make_pdf(), "test_invoice.pdf")
    assert "RAI-TEST-1001" in pdf["text"]
    assert pdf["metadata"]["page_count"] == 1
    print("PASS: test_invoice.pdf")

    mixed_pdf = pymupdf.open()
    normal_page = mixed_pdf.new_page()
    normal_page.insert_text(
        (72, 72),
        "This page contains enough native text for extraction.",
    )
    mixed_pdf.new_page()
    mixed_pdf_bytes = mixed_pdf.tobytes()
    mixed_pdf.close()
    with patch.object(
        pymupdf.Page,
        "get_textpage_ocr",
        side_effect=RuntimeError("simulated OCR failure"),
    ):
        partial_pdf = extract_uploaded_file(
            mixed_pdf_bytes,
            "partial_ocr.pdf",
        )
    assert "native text for extraction" in partial_pdf["text"]
    assert any("OCR failed on page 2" in warning
               for warning in partial_pdf["warnings"])

    word = extract_uploaded_file(make_docx(), "test_invoice.docx")
    assert "RAI-TEST-1002" in word["text"]
    assert "Consulting" in word["text"]
    assert len(word["tables"]) == 1
    print("PASS: test_invoice.docx")

    excel = extract_uploaded_file(make_xlsx(), "test_invoices.xlsx")
    assert len(excel["records"]) == 2
    assert excel["metadata"]["worksheet_names"] == [
        "Invoices",
        "Other Invoices",
    ]
    print("PASS: test_invoices.xlsx")

    csv = extract_uploaded_file(make_csv(), "test_invoices.csv")
    assert len(csv["records"]) == 2
    print("PASS: test_invoices.csv")

    expect_value_error(b"plain text", "test.txt")
    expect_value_error(b"", "empty.csv")
    expect_value_error(b"not a pdf", "invalid.pdf")
    expect_value_error(b"PKnot-a-docx", "invalid.docx")
    expect_value_error(b"PKnot-an-xlsx", "invalid.xlsx")
    expect_value_error(b"not an xls", "invalid.xls")

    empty_workbook = Workbook()
    empty_output = BytesIO()
    empty_workbook.save(empty_output)
    empty_workbook.close()
    empty_result = extract_uploaded_file(
        empty_output.getvalue(),
        "empty.xlsx",
    )
    assert not empty_result["records"]
    assert empty_result["warnings"]

    csv_without_currency = (
        b"invoice_number,customer_name,amount\n"
        b"RAI-TEST-1007,Customer C,300\n"
    )
    missing_currency = extract_uploaded_file(
        csv_without_currency,
        "missing_currency.csv",
    )
    assert any("Currency column is missing" in warning
               for warning in missing_currency["warnings"])
    assert missing_currency["records"][0].get("amount_aed") is None

    legacy_csv_without_currency = (
        b"invoice_number,customer_name,amount,issue_date,due_date\n"
        b"RAI-TEST-1007,Customer C,300,2026-01-01,2026-01-10\n"
    )
    legacy_row = extract_csv_rows(legacy_csv_without_currency)[0]
    assert legacy_row["fields"]["amount_aed"] is None
    assert any("Do not assume" in note for note in legacy_row["notes"])

    foreign_currency = (
        b"invoice_number,customer_name,amount,currency\n"
        b"RAI-TEST-1008,Customer D,400,USD\n"
    )
    foreign_result = extract_csv(foreign_currency)
    assert foreign_result["records"][0]["amount"] == "400"
    assert foreign_result["records"][0].get("amount_aed") is None
    assert any("non-AED" in warning for warning in foreign_result["warnings"])

    cp1252_csv = (
        b"invoice_number,customer_name\n"
        b"RAI-TEST-1009,Caf\xe9\n"
    )
    cp1252_result = extract_uploaded_file(cp1252_csv, "cp1252.csv")
    assert cp1252_result["records"][0]["customer_name"] == "Café"

    formula_workbook = Workbook()
    formula_workbook.active["A1"] = "Amount"
    formula_workbook.active["A2"] = "=SUM(1,2)"
    formula_output = BytesIO()
    formula_workbook.save(formula_output)
    formula_workbook.close()
    formula_result = extract_uploaded_file(
        formula_output.getvalue(),
        "formula.xlsx",
    )
    assert any("formula without a cached result" in warning
               for warning in formula_result["warnings"])

    print("All four extractor tests passed.")


if __name__ == "__main__":
    run_tests()
