from app.services.invoice_column_mapper import map_columns
from app.services.privacy_filter import sanitize_column_headings


def test_known_register_columns_map_without_fuzzy_overwrites():
    result = map_columns([
        "Invoice Number",
        "Supplier Name",
        "Supplier TRN",
        "Buyer Name",
        "VAT Rate (%)",
        "Taxable Value",
        "VAT Amount",
        "Grand Total",
    ])
    assert result["resolved"] == {
        "invoice_number": "Invoice Number",
        "supplier_name": "Supplier Name",
        "supplier_trn": "Supplier TRN",
        "customer_name": "Buyer Name",
        "vat_rate": "VAT Rate (%)",
        "taxable_value_aed": "Taxable Value",
        "vat_amount_aed": "VAT Amount",
        "total_amount_aed": "Grand Total",
    }
    assert not result["conflicts"]
    assert not result["ambiguous"]


def test_duplicate_columns_targeting_same_field_are_conflicts():
    result = map_columns(["Invoice Number", "Invoice No"])
    assert "invoice_number" not in result["resolved"]
    assert result["conflicts"] == {
        "invoice_number": ["Invoice Number", "Invoice No"]
    }


def test_unknown_headings_are_unresolved_and_sensitive_headings_omitted():
    result = map_columns([
        "Invoice Reference",
        "John Smith - confidential account",
    ])
    assert result["resolved"] == {"invoice_number": "Invoice Reference"}
    assert result["unresolved"] == ["John Smith - confidential account"]
    assert sanitize_column_headings(result["unresolved"]) == {}


def test_financial_labels_keep_distinct_meaning():
    result = map_columns(["Subtotal", "Discount", "VAT Amount", "Grand Total"])
    assert result["resolved"] == {
        "subtotal_aed": "Subtotal",
        "discount_aed": "Discount",
        "vat_amount_aed": "VAT Amount",
        "total_amount_aed": "Grand Total",
    }
