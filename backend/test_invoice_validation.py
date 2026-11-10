from decimal import Decimal

from app.services.invoice_validator import (
    calculate_invoice_item,
    calculate_invoice_totals,
    parse_invoice_date,
    parse_invoice_amount,
    validate_invoice,
    validate_trn,
)


def line_item(**overrides):
    item = {
        "description": "T Shirts",
        "quantity": Decimal("1000"),
        "unit_price_aed": Decimal("100"),
        "discount_aed": Decimal("0"),
        "taxable_value_aed": Decimal("100000"),
        "vat_rate": Decimal("5"),
        "vat_amount_aed": Decimal("5000"),
        "line_total_aed": Decimal("105000"),
    }
    item.update(overrides)
    return item


def valid_invoice(**overrides):
    invoice = {
        "invoice_number": "INV-001",
        "supplier_name": "Test Supplier",
        "supplier_trn": "100123456700003",
        "customer_name": "Test Buyer",
        "customer_trn": "100987654300003",
        "currency": "AED",
        "issue_date": "2026-10-01",
        "supply_date": "2026-10-01",
        "due_date": "2026-11-01",
        "items": [line_item()],
        "subtotal_aed": Decimal("100000"),
        "vat_amount_aed": Decimal("5000"),
        "total_amount_aed": Decimal("105000"),
        "amount_aed": Decimal("105000"),
        "duplicate": {"status": "clear"},
    }
    invoice.update(overrides)
    return invoice


def run_tests():
    print("RECEIVAI INVOICE VALIDATION TEST")

    # 1. Standard 15-digit UAE TRN format.
    assert validate_trn("100123456700003")["is_valid_format"]
    print("PASS 1: valid UAE TRN")

    # 2. Spaces and hyphens are formatting only.
    assert validate_trn("100 123-456 700003")["value"] == "100123456700003"
    assert validate_trn("100 123-456 700003")["is_valid_format"]
    print("PASS 2: formatted UAE TRN")

    # 3-5. Invalid length, letters and missing TRNs are distinguished.
    assert not validate_trn("12345678901234")["is_valid_format"]
    assert not validate_trn("10012345670000A")["is_valid_format"]
    missing_trn = validate_trn(None)
    assert not missing_trn["is_present"] and not missing_trn["is_valid_format"]
    print("PASS 3-5: invalid and missing TRNs")

    # 6-8. Date parsing and chronology.
    assert parse_invoice_date("2026-10-01").isoformat() == "2026-10-01"
    assert parse_invoice_date("01/10/2026").isoformat() == "2026-10-01"
    assert parse_invoice_date("01-10-2026").isoformat() == "2026-10-01"
    assert parse_invoice_date("01/10/26").isoformat() == "2026-10-01"
    earlier_due = validate_invoice(valid_invoice(
        due_date="2026-09-01",
    ))
    assert "Due date cannot be earlier than invoice issue date." in earlier_due["errors"]
    assert parse_invoice_date("31/02/2026") is None
    assert parse_invoice_amount("AED 1,000.25") == Decimal("1000.25")
    assert parse_invoice_amount("100.25 د.إ") == Decimal("100.25")
    print("PASS 6-8: date formats and date validation")

    # 9-11. VAT calculation supports 5%, 0% and differing explicit rates.
    five_percent = calculate_invoice_item(line_item())
    assert five_percent["calculated"]["taxable_value_aed"] == "100000.00"
    assert five_percent["calculated"]["vat_amount_aed"] == "5000.00"
    assert five_percent["calculated"]["line_total_aed"] == "105000.00"
    zero_rate = calculate_invoice_item(line_item(
        quantity=Decimal("1"),
        unit_price_aed=Decimal("100"),
        taxable_value_aed=Decimal("100"),
        vat_rate=Decimal("0"),
        vat_amount_aed=Decimal("0"),
        line_total_aed=Decimal("100"),
    ))
    assert zero_rate["calculated"]["vat_amount_aed"] == "0.00"
    mixed = calculate_invoice_totals([
        line_item(quantity=Decimal("1"), unit_price_aed=Decimal("100"),
                  taxable_value_aed=Decimal("100"), vat_rate=Decimal("5"),
                  vat_amount_aed=Decimal("5"), line_total_aed=Decimal("105")),
        line_item(quantity=Decimal("1"), unit_price_aed=Decimal("100"),
                  taxable_value_aed=Decimal("100"), vat_rate=Decimal("0"),
                  vat_amount_aed=Decimal("0"), line_total_aed=Decimal("100")),
    ])
    assert mixed["vat_amount_aed"] == "5.00"
    print("PASS 9-11: 5%, 0%, and mixed VAT calculations")

    # 12. Extracted line VAT discrepancies are surfaced.
    wrong_vat = calculate_invoice_item(line_item(vat_amount_aed=Decimal("4000")))
    assert any("vat amount" in warning for warning in wrong_vat["warnings"])
    print("PASS 12: inconsistent line VAT is flagged")

    # 13-14. Correct and incorrect invoice grand totals.
    assert validate_invoice(valid_invoice())["is_valid"]
    bad_total = validate_invoice(valid_invoice(total_amount_aed=Decimal("104999")))
    assert any("total amount" in error for error in bad_total["errors"])
    print("PASS 13-14: grand-total reconciliation")

    # 15. Discounts reduce taxable value before VAT.
    discounted = calculate_invoice_item(line_item(
        quantity=Decimal("1"),
        unit_price_aed=Decimal("100"),
        discount_aed=Decimal("10"),
        taxable_value_aed=Decimal("90"),
        vat_rate=Decimal("5"),
        vat_amount_aed=Decimal("4.50"),
        line_total_aed=Decimal("94.50"),
    ))
    assert discounted["calculated"]["taxable_value_aed"] == "90.00"
    assert discounted["calculated"]["vat_amount_aed"] == "4.50"
    print("PASS 15: line discount calculation")

    # 16. Currency must be explicit; no AED assumption is made.
    no_currency = validate_invoice(valid_invoice(currency=None))
    assert any("Currency is missing" in error for error in no_currency["errors"])
    assert any("Currency is missing" in warning for warning in no_currency["warnings"])
    print("PASS 16: missing currency is rejected for AED approval")

    # 17-18. Negative quantities and unit prices cannot be approved.
    assert not calculate_invoice_item(line_item(quantity=Decimal("-1")))["is_valid"]
    assert not calculate_invoice_item(line_item(unit_price_aed=Decimal("-1")))["is_valid"]
    print("PASS 17-18: negative quantity and price")

    # 19. Registered invoices and duplicate uploads block approval.
    duplicate = validate_invoice(valid_invoice(
        duplicate={"status": "same_invoice", "message": "Already registered."},
    ))
    assert not duplicate["is_valid"] and "Already registered." in duplicate["errors"]
    upload_duplicate = validate_invoice(valid_invoice(
        duplicate={
            "status": "duplicate_upload",
            "message": "Exact document was already uploaded.",
        },
    ))
    assert not upload_duplicate["is_valid"]
    assert "Exact document was already uploaded." in upload_duplicate["errors"]
    conflicting = validate_invoice(valid_invoice(
        duplicate={
            "status": "conflicting_number",
            "message": "Invoice number belongs to another supplier.",
        },
    ))
    assert not conflicting["is_valid"]
    uncertain = validate_invoice(valid_invoice(
        duplicate={"status": "ambiguous", "message": "Confirm supplier identity."},
    ))
    assert uncertain["review_required"]
    assert "Confirm supplier identity." in uncertain["warnings"]
    print("PASS 19: registered, conflicting and duplicate-upload checks")

    # 20. Multiple rows are summed independently.
    totals = calculate_invoice_totals([
        line_item(quantity=Decimal("1"), unit_price_aed=Decimal("100"),
                  taxable_value_aed=Decimal("100"), vat_rate=Decimal("5"),
                  vat_amount_aed=Decimal("5"), line_total_aed=Decimal("105")),
        line_item(quantity=Decimal("2"), unit_price_aed=Decimal("50"),
                  taxable_value_aed=Decimal("100"), vat_rate=Decimal("0"),
                  vat_amount_aed=Decimal("0"), line_total_aed=Decimal("100")),
    ])
    assert totals["subtotal_aed"] == "200.00"
    assert totals["vat_amount_aed"] == "5.00"
    assert totals["total_amount_aed"] == "205.00"
    print("PASS 20: multiple line items")

    # 21. Monetary rounding uses ROUND_HALF_UP.
    rounded = calculate_invoice_item(line_item(
        quantity=Decimal("1"),
        unit_price_aed=Decimal("1.005"),
        taxable_value_aed=Decimal("1.01"),
        vat_rate=Decimal("5"),
        vat_amount_aed=Decimal("0.05"),
        line_total_aed=Decimal("1.06"),
    ))
    assert rounded["calculated"]["gross_value_aed"] == "1.01"
    assert rounded["calculated"]["line_total_aed"] == "1.06"
    quantity_precision = calculate_invoice_item(line_item(
        quantity=Decimal("1.2345"),
        unit_price_aed=Decimal("1"),
        taxable_value_aed=Decimal("1.24"),
        vat_rate=Decimal("0"),
        vat_amount_aed=Decimal("0"),
        line_total_aed=Decimal("1.24"),
    ))
    assert quantity_precision["extracted"]["quantity"] == "1.235"
    print("PASS 21: two-place ROUND_HALF_UP rounding")

    # 22. Invoice-level discounts matching the line discounts are not subtracted twice.
    no_double_discount = calculate_invoice_totals(
        [line_item(
            quantity=Decimal("1"),
            unit_price_aed=Decimal("100"),
            discount_aed=Decimal("10"),
            taxable_value_aed=Decimal("90"),
            vat_rate=Decimal("5"),
            vat_amount_aed=Decimal("4.50"),
            line_total_aed=Decimal("94.50"),
        )],
        invoice_discount_aed=Decimal("10"),
    )
    assert no_double_discount["discount_aed"] == "10.00"
    assert no_double_discount["total_amount_aed"] == "94.50"
    assert (
        no_double_discount["invoice_discount_allocation_method"]
        == "included_in_line_discounts"
    )
    print("PASS 22: invoice discount is not counted twice")
    print("All 22 invoice validation tests passed.")


if __name__ == "__main__":
    run_tests()
