from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.routes import documents
from app.models import InvoiceDocument


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeDatabase:
    def __init__(self, document):
        self.document = document
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, key):
        if model is InvoiceDocument and key == self.document.id:
            return self.document
        return None

    def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        return FakeScalars(
            [self.document] if entity is InvoiceDocument else []
        )

    def add(self, item):
        del item

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, item):
        del item


def run_tests():
    original_storage_dir = documents.settings.invoice_storage_dir
    original_extract_file = documents.extract_uploaded_file
    original_extract_document = documents.document_agent.extract_document
    original_audit_log = documents.create_audit_log
    try:
        with TemporaryDirectory() as storage_dir:
            documents.settings.invoice_storage_dir = storage_dir
            source_path = Path(storage_dir) / "retry.pdf"
            source_path.write_bytes(b"%PDF-1.4\nsynthetic invoice")
            document = InvoiceDocument(
                id=81,
                invoice_id=None,
                original_filename="retry.pdf",
                storage_path=str(source_path),
                mime_type="application/pdf",
                processing_status="uploaded",
                extraction_notes=None,
                extracted_data={"file_type": "pdf"},
            )
            db = FakeDatabase(document)
            admin = SimpleNamespace(id=9)
            attempts = {"count": 0}

            def extract_file(**kwargs):
                del kwargs
                return {"metadata": {}, "warnings": [], "records": []}

            def extract_document(raw_extraction):
                del raw_extraction
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise ValueError("Synthetic extraction failure")
                return {
                    "invoices": [{
                        "invoice_number": "RETRY-001",
                        "customer_name": "Test Buyer",
                        "supplier_name": "Test Supplier",
                        "currency": "AED",
                        "issue_date": "2026-10-01",
                        "due_date": "2026-11-01",
                        "total_amount_aed": "105.00",
                        "items": [],
                    }],
                    "extraction_notes": [],
                }

            documents.extract_uploaded_file = extract_file
            documents.document_agent.extract_document = extract_document
            documents.create_audit_log = lambda **kwargs: None

            try:
                documents.process_document(document.id, db, admin)
            except HTTPException as exc:
                assert exc.status_code == 422
            else:
                raise AssertionError("The first processing attempt should fail.")

            assert document.processing_status == "processing_failed"
            retry_result = documents.retry_document_processing(
                document.id, db, admin
            )
            assert document.processing_status == "pending_review"
            assert attempts["count"] == 2
            assert len(document.extracted_data["processing_attempts"]) == 2
            assert retry_result["document"]["processing_status"] == "pending_review"
            assert "storage_path" not in retry_result["document"]

            pending = documents.get_pending_documents(db)
            assert pending["count"] == 1
            assert pending["documents"][0]["id"] == document.id
            detail = documents.get_document(document.id, db)
            assert "storage_path" not in detail
            assert db.commits >= 3

        print("PASS: failed processing retries the same private document")
        print("PASS: pending and detail responses omit private storage paths")
    finally:
        documents.settings.invoice_storage_dir = original_storage_dir
        documents.extract_uploaded_file = original_extract_file
        documents.document_agent.extract_document = original_extract_document
        documents.create_audit_log = original_audit_log


if __name__ == "__main__":
    run_tests()
