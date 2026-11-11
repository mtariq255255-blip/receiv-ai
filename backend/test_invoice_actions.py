from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.routes import invoices
from app.models import AuditLog
from app.schemas.invoice import (
    InvoiceCorrectionRequest,
    InvoiceStatusUpdate,
)


class FakeDatabase:
    def __init__(self, invoice):
        self.invoice = invoice
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, key):
        return self.invoice if key == self.invoice.id else None

    def scalar(self, statement):
        del statement
        return None

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, item):
        del item


def new_invoice():
    return SimpleNamespace(
        id=33,
        invoice_number="INV-ACT-001",
        customer_name="Example Buyer",
        customer_email=None,
        amount_aed=100,
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
        status="overdue",
        source_type="pdf",
        review_status="reviewed",
        notes=None,
        supplier_name="Example Supplier",
        supplier_trn="100123456700003",
    )


def run_tests():
    admin = SimpleNamespace(id=9)

    invoice = new_invoice()
    db = FakeDatabase(invoice)
    invoices.update_invoice_status(
        invoice.id, InvoiceStatusUpdate(status="paid"), db, admin
    )
    assert invoice.status == "paid"
    assert db.commits == 1
    audit = next(item for item in db.added if isinstance(item, AuditLog))
    assert audit.details == {
        "previous_status": "overdue",
        "new_status": "paid",
        "method": "manual_status_only",
    }

    invoices.update_invoice_status(
        invoice.id, InvoiceStatusUpdate(status="unpaid"), db, admin
    )
    assert invoice.status == "overdue"
    print("PASS: paid status can be set and reversed with audit history")

    invoice = new_invoice()
    db = FakeDatabase(invoice)
    correction = InvoiceCorrectionRequest(
        reason="Corrected customer details from the source invoice.",
        customer_name="Corrected Buyer",
        customer_email="ap@example.test",
    )
    invoices.correct_approved_invoice(invoice.id, correction, db, admin)
    assert invoice.customer_name == "Corrected Buyer"
    assert invoice.customer_email == "ap@example.test"
    assert invoice.review_status == "corrected"
    audit = next(item for item in db.added if isinstance(item, AuditLog))
    assert audit.details["before"]["customer_name"] == "Example Buyer"
    assert audit.details["after"]["customer_name"] == "Corrected Buyer"
    assert audit.details["reason"].startswith("Corrected customer")
    print("PASS: approved invoice correction stores before/after and reason")

    invoice = new_invoice()
    db = FakeDatabase(invoice)
    correction = InvoiceCorrectionRequest(
        reason="Correct the dates.",
        issue_date=date(2026, 11, 1),
    )
    try:
        invoices.correct_approved_invoice(invoice.id, correction, db, admin)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Correction must reject due dates before issue date.")
    assert db.commits == 0
    print("PASS: invoice corrections preserve date ordering")


if __name__ == "__main__":
    run_tests()
