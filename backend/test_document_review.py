from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine

from app.api.routes import documents
from app.models import Invoice, InvoiceDocument, InvoiceItem
from app.schemas.invoice import InvoiceReviewItem, InvoiceReviewRequest
from app.schemas.uae_invoice import CompleteInvoiceValidationResponse


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeDatabase:
    def __init__(
        self,
        document,
        existing=None,
        documents=None,
        fail_on_item=False,
    ):
        self.document = document
        self.existing = existing or []
        self.documents = documents or []
        self.fail_on_item = fail_on_item
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, key):
        return self.document if model is InvoiceDocument and key == self.document.id else None

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is InvoiceDocument:
            return FakeScalars(self.documents)
        return FakeScalars(self.existing)

    def add(self, item):
        if self.fail_on_item and isinstance(item, InvoiceItem):
            raise RuntimeError("Simulated invoice item persistence failure")
        self.added.append(item)

    def flush(self):
        for added_item in self.added:
            if isinstance(added_item, Invoice):
                added_item.id = 42

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, item):
        del item


def new_document():
    source_invoice = {
        "invoice_number": "INV-REVIEW-001",
        "supplier_name": "Review Supplier",
        "supplier_trn": "100123456700003",
        "customer_name": "Review Buyer",
        "customer_trn": "100987654300003",
        "customer_email": None,
        "currency": "AED",
        "issue_date": "2026-10-01",
        "supply_date": "2026-10-01",
        "due_date": "2026-12-01",
        "items": [{
            "description": "Service",
            "quantity": "1",
            "unit": "each",
            "unit_price_aed": "100.00",
            "discount_aed": "0.00",
            "taxable_value_aed": "100.00",
            "vat_rate": "5.00",
            "vat_amount_aed": "5.00",
            "line_total_aed": "105.00",
        }],
        "subtotal_aed": "100.00",
        "discount_aed": "0.00",
        "vat_amount_aed": "5.00",
        "total_amount_aed": "105.00",
    }
    return InvoiceDocument(
        id=7,
        invoice_id=None,
        original_filename="review.pdf",
        storage_path="private/review.pdf",
        processing_status="pending_review",
        extracted_data={
            "content_sha256": "current-document-hash",
            "structured_invoice": source_invoice,
            "fields": {
                "invoice_number": source_invoice["invoice_number"],
                "customer_name": source_invoice["customer_name"],
                "amount_aed": "105.00",
                "issue_date": source_invoice["issue_date"],
                "due_date": source_invoice["due_date"],
            },
        },
    )


def review_request(amount=Decimal("105.00")):
    return InvoiceReviewRequest(
        invoice_number="INV-REVIEW-001",
        supplier_name="Review Supplier",
        supplier_trn="100123456700003",
        customer_name="Review Buyer",
        customer_trn="100987654300003",
        currency="AED",
        amount_aed=amount,
        subtotal_aed=Decimal("100.00"),
        discount_aed=Decimal("0.00"),
        vat_amount_aed=Decimal("5.00"),
        total_amount_aed=Decimal("105.00"),
        issue_date=date(2026, 10, 1),
        supply_date=date(2026, 10, 1),
        due_date=date(2026, 12, 1),
        items=[InvoiceReviewItem(
            description="Service",
            quantity=Decimal("1"),
            unit="each",
            unit_price_aed=Decimal("100.00"),
            discount_aed=Decimal("0.00"),
            taxable_value_aed=Decimal("100.00"),
            vat_rate=Decimal("5"),
            vat_amount_aed=Decimal("5.00"),
            line_total_aed=Decimal("105.00"),
        )],
    )


def validate_for_approval(document, db, request, admin):
    return documents.validate_document_invoice(
        document.id, request, db, admin
    )


def verify_invoice_timestamp_defaults():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Invoice.__table__.create(engine)
        with engine.begin() as connection:
            inserted = connection.execute(
                Invoice.__table__.insert().values(
                    id=1,
                    invoice_number="TIMESTAMP-TEST",
                    customer_name="Timestamp Test",
                    amount_aed=Decimal("10.00"),
                    issue_date=date(2026, 10, 1),
                    due_date=date(2026, 11, 1),
                    status="unpaid",
                    source_type="pdf",
                    review_status="reviewed",
                ).returning(
                    Invoice.__table__.c.created_at,
                    Invoice.__table__.c.updated_at,
                )
            ).one()
            assert inserted.created_at is not None
            assert inserted.updated_at is not None

            updated = connection.execute(
                Invoice.__table__.update()
                .where(Invoice.__table__.c.invoice_number == "TIMESTAMP-TEST")
                .values(notes="Updated")
                .returning(Invoice.__table__.c.updated_at)
            ).one()
            assert updated.updated_at is not None
    finally:
        engine.dispose()


def run_tests():
    original_audit = documents.create_audit_log

    def no_audit_log(**kwargs):
        del kwargs

    documents.create_audit_log = no_audit_log
    admin = SimpleNamespace(id=1)
    try:
        verify_invoice_timestamp_defaults()
        print("PASS: invoice timestamps default on insert and update")

        # Corrected invoice values validate and persist validation JSON for review.
        document = new_document()
        db = FakeDatabase(document)
        validation = documents.validate_document_invoice(
            document.id, review_request(), db, admin
        )
        CompleteInvoiceValidationResponse.model_validate(validation)
        assert validation["is_valid"]
        assert document.extracted_data["validation"]["calculated_totals"]["total_amount_aed"] == "105.00"
        assert db.commits == 1
        print("PASS: review validation persists calculated totals")

        document = new_document()
        db = FakeDatabase(document)
        details = documents.correct_document_invoice(
            document.id, review_request(), db, admin
        )
        assert document.extracted_data["invoice_reviews"]["0"]["invoice_number"] == (
            "INV-REVIEW-001"
        )
        assert details["processing_status"] == "pending_review"
        assert "storage_path" not in details
        assert "storage_path" not in documents.document_to_response(document)
        print("PASS: corrections are persisted without exposing private paths")

        # Approval stores a deterministic invoice and its item atomically.
        document = new_document()
        document.original_filename = "register.xlsx"
        db = FakeDatabase(document)
        validate_for_approval(document, db, review_request(), admin)
        db.commits = 0
        response = documents.review_invoice_document(
            document.id, review_request(), db, admin
        )
        saved_invoice = next(item for item in db.added if isinstance(item, Invoice))
        saved_item = next(item for item in db.added if isinstance(item, InvoiceItem))
        assert response.amount_aed == "105.00"
        assert saved_invoice.amount_aed == Decimal("105.00")
        assert saved_invoice.source_type == "xlsx"
        assert saved_item.line_total_aed == Decimal("105.00")
        assert document.invoice_id == 42
        assert db.commits == 1 and db.rollbacks == 0
        print("PASS: approval saves calculated invoice and line item")

        document = new_document()
        second_invoice = {
            **document.extracted_data["structured_invoice"],
            "invoice_number": "INV-REVIEW-002",
        }
        document.extracted_data["structured_extraction"] = {
            "invoices": [
                document.extracted_data["structured_invoice"],
                second_invoice,
            ],
        }
        db = FakeDatabase(document)
        second_request = review_request().model_copy(update={
            "invoice_index": 1,
            "invoice_number": "INV-REVIEW-002",
        })
        validate_for_approval(document, db, second_request, admin)
        documents.review_invoice_document(document.id, second_request, db, admin)
        assert document.processing_status == "pending_review"
        assert document.extracted_data["approved_invoice_indices"] == [1]
        try:
            documents.validate_document_invoice(
                document.id, second_request, db, admin
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("An approved spreadsheet invoice must be immutable.")

        first_request = review_request()
        validate_for_approval(document, db, first_request, admin)
        documents.review_invoice_document(document.id, first_request, db, admin)
        assert document.processing_status == "approved"
        assert document.extracted_data["approved_invoice_indices"] == [0, 1]
        print("PASS: spreadsheet invoices are approved independently")

        # A clearly stated total can be approved without invented line items.
        document = new_document()
        db = FakeDatabase(document)
        total_only = review_request().model_copy(update={"items": []})
        validate_for_approval(document, db, total_only, admin)
        documents.review_invoice_document(document.id, total_only, db, admin)
        assert any(isinstance(item, Invoice) for item in db.added)
        assert not any(isinstance(item, InvoiceItem) for item in db.added)
        print("PASS: total-only invoices do not require fabricated items")

        # Financial mismatches block approval and create no invoice records.
        document = new_document()
        db = FakeDatabase(document)
        mismatched = review_request(Decimal("104.00"))
        validate_for_approval(document, db, mismatched, admin)
        try:
            documents.review_invoice_document(
                document.id, mismatched, db, admin
            )
        except HTTPException as exc:
            assert exc.status_code == 422
            assert not any(isinstance(item, Invoice) for item in db.added)
        else:
            raise AssertionError("Mismatched invoice amount should not be approved.")
        print("PASS: validation errors prevent approval")

        # A same-supplier invoice number is explicitly identified as duplicate.
        document = new_document()
        existing = SimpleNamespace(
            invoice_number="INV-REVIEW-001",
            supplier_name="Review Supplier",
            supplier_trn="100123456700003",
            id=99,
        )
        db = FakeDatabase(document, existing=[existing])
        validate_for_approval(document, db, review_request(), admin)
        try:
            documents.review_invoice_document(
                document.id, review_request(), db, admin
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            assert not any(isinstance(item, Invoice) for item in db.added)
        else:
            raise AssertionError("A same-supplier duplicate should not be approved.")
        print("PASS: same-supplier duplicate invoices are blocked")

        # Reused numbers from other suppliers are not classified as identical.
        document = new_document()
        unrelated_supplier = SimpleNamespace(
            invoice_number="INV-REVIEW-001",
            supplier_name="Unrelated Supplier",
            supplier_trn="100111111100003",
            id=100,
        )
        db = FakeDatabase(document, existing=[unrelated_supplier])
        conflict = documents._duplicate_invoice_check(
            db,
            {
                "invoice_number": "INV-REVIEW-001",
                "supplier_name": "Review Supplier",
                "supplier_trn": "100123456700003",
            },
        )
        assert conflict["status"] == "conflicting_number"
        assert conflict["matches"][0]["supplier_name"] == "Unrelated Supplier"
        assert conflict["matches"][0]["supplier_trn"] == "100111111100003"
        print("PASS: conflicting supplier details are returned")

        document = new_document()
        db = FakeDatabase(document, existing=[unrelated_supplier])
        validation = validate_for_approval(document, db, review_request(), admin)
        assert validation["checks"]["duplicate"]["status"] == "conflicting_number"
        try:
            documents.review_invoice_document(
                document.id, review_request(), db, admin
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail["matches"][0]["supplier_trn"] == "100111111100003"
        else:
            raise AssertionError("A conflicting invoice number must not be approved.")
        print("PASS: conflicting supplier numbers block approval with details")

        # Demo seed rows never create a genuine duplicate warning.
        document = new_document()
        demo_invoice = SimpleNamespace(
            invoice_number="INV-REVIEW-001",
            supplier_name=None,
            supplier_trn=None,
            source_type="demo",
            source_filename="demo.pdf",
            id=101,
        )
        db = FakeDatabase(document, existing=[demo_invoice])
        validation = validate_for_approval(document, db, review_request(), admin)
        assert validation["is_valid"]
        assert validation["checks"]["duplicate"]["status"] == "clear"
        assert validation["checks"]["duplicate"]["ignored_demo_matches"][0][
            "invoice_id"
        ] == 101
        documents.review_invoice_document(
            document.id, review_request(), db, admin
        )
        print("PASS: demo invoice collisions do not block genuine invoices")

        # The current linked invoice is excluded from duplicate comparisons.
        document = new_document()
        document.invoice_id = 102
        self_invoice = SimpleNamespace(
            invoice_number="INV-REVIEW-001",
            supplier_name="Review Supplier",
            supplier_trn="100123456700003",
            source_type="pdf",
            source_filename="review.pdf",
            id=102,
        )
        db = FakeDatabase(document, existing=[self_invoice])
        duplicate = documents._duplicate_invoice_check(
            db,
            {
                "invoice_number": "INV-REVIEW-001",
                "supplier_name": "Review Supplier",
                "supplier_trn": "100123456700003",
            },
            document,
        )
        assert duplicate["status"] == "clear"
        print("PASS: current invoice is excluded from self-comparison")

        # Exact document re-uploads are distinguished from invoice-number conflicts.
        document = new_document()
        existing_document = SimpleNamespace(
            id=103,
            extracted_data={"content_sha256": "current-document-hash"},
            storage_path="missing-existing-document.pdf",
            original_filename="review-copy.pdf",
            processing_status="pending_review",
        )
        db = FakeDatabase(document, documents=[existing_document])
        validation = validate_for_approval(document, db, review_request(), admin)
        assert validation["checks"]["duplicate"]["status"] == "duplicate_upload"
        try:
            documents.review_invoice_document(
                document.id, review_request(), db, admin
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail["matches"][0]["document_id"] == 103
        else:
            raise AssertionError("A duplicate document upload must not be approved.")
        print("PASS: identical document uploads block approval with details")

        document = new_document()
        rejected_copy = SimpleNamespace(
            id=104,
            extracted_data={"content_sha256": "current-document-hash"},
            storage_path="missing-rejected-copy.pdf",
            original_filename="review-copy.pdf",
            processing_status="rejected",
        )
        db = FakeDatabase(document, documents=[rejected_copy])
        validation = validate_for_approval(document, db, review_request(), admin)
        assert validation["checks"]["duplicate"]["status"] == "clear"
        documents.review_invoice_document(
            document.id, review_request(), db, admin
        )
        assert any(isinstance(item, Invoice) for item in db.added)
        print("PASS: explicitly rejected upload duplicates no longer block approval")

        clear = documents._duplicate_invoice_check(
            FakeDatabase(new_document()),
            {
                "invoice_number": "INV-REVIEW-NEW",
                "supplier_name": "New Supplier",
                "supplier_trn": "100444444400003",
            },
        )
        assert clear["status"] == "clear"
        print("PASS: nonduplicate invoices remain clear")

        # Failure while inserting a line item rolls the invoice transaction back.
        document = new_document()
        db = FakeDatabase(document, fail_on_item=True)
        validate_for_approval(document, db, review_request(), admin)
        db.commits = 0
        try:
            documents.review_invoice_document(
                document.id, review_request(), db, admin
            )
        except HTTPException as exc:
            assert exc.status_code == 500
            assert db.rollbacks == 1 and db.commits == 0
        else:
            raise AssertionError("Line-item save failure should roll back approval.")
        print("PASS: invoice and item save failure rolls back")
    finally:
        documents.create_audit_log = original_audit
    print("All document review tests passed.")


if __name__ == "__main__":
    run_tests()
