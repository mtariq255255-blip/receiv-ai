import json
import logging

from app.core.config import settings
from app.schemas.uae_invoice import UAEInvoiceExtractionSchema
from app.services.invoice_column_mapper import map_columns
from app.services.local_invoice_parser import parse_local_invoices
from app.services.private_ai_gateway import (
    PrivateAIError,
    map_invoice_columns_with_ai,
)
from app.services.privacy_filter import (
    PrivacyContext,
    PrivacyViolationError,
    protect_value,
)
from app.services.privacy_router import ProcessingMode, choose_processing_mode


logger = logging.getLogger(__name__)

class DocumentIntelligenceAgent:
    """Extract untrusted document content into reviewable invoice data."""

    @staticmethod
    def _annotate_invoice(
        invoice: UAEInvoiceExtractionSchema,
        filename: str,
        warnings: list[str] | None = None,
    ) -> UAEInvoiceExtractionSchema:
        invoice.source_filename = invoice.source_filename or filename
        fields = (
            "invoice_number",
            "supplier_name",
            "supplier_address",
            "supplier_emirate",
            "supplier_trn",
            "customer_name",
            "customer_address",
            "customer_emirate",
            "customer_trn",
            "issue_date",
            "supply_date",
            "due_date",
            "place_of_supply",
            "currency",
            "subtotal_aed",
            "discount_aed",
            "vat_amount_aed",
            "total_amount_aed",
        )
        invoice.missing_fields = sorted(set(
            invoice.missing_fields
            + [name for name in fields if getattr(invoice, name) is None]
            + (["items"] if not invoice.items else [])
        ))
        invoice.extraction_notes = list(dict.fromkeys(
            invoice.extraction_notes + (warnings or [])
        ))
        return invoice

    @staticmethod
    def _serialize_input(content: str | dict) -> tuple[str, dict]:
        if isinstance(content, str):
            text = content.strip()
            return text, {"text": text}
        if not isinstance(content, dict):
            raise ValueError("Document content must be text or an extraction result.")

        text = content.get("text", "")
        records = content.get("records", [])
        tables = content.get("tables", [])
        metadata = content.get("metadata") or {}
        warnings = content.get("warnings") or []
        paragraphs = content.get("paragraphs", [])
        blocks = content.get("blocks", [])
        if (
            not isinstance(text, str)
            or not isinstance(records, list)
            or not isinstance(tables, list)
            or not isinstance(metadata, dict)
            or not isinstance(warnings, list)
            or not isinstance(paragraphs, list)
            or not isinstance(blocks, list)
        ):
            raise ValueError("Document extraction result has an invalid structure.")

        normalized = {
            "filename": str(content.get("filename") or "unknown"),
            "file_type": str(content.get("file_type") or "unknown"),
            "text": text,
            "records": records,
            "tables": tables,
            "metadata": metadata,
            "warnings": warnings,
            "paragraphs": paragraphs,
            "blocks": blocks,
        }
        rendered = json.dumps(normalized, ensure_ascii=False, default=str)
        return rendered, normalized

    def extract_invoice(
        self,
        extracted_content: str | dict,
    ) -> UAEInvoiceExtractionSchema:
        """Parse one invoice locally; raw document content is never submitted."""
        _, normalized = self._serialize_input(extracted_content)
        parsed = parse_local_invoices(normalized)
        invoices = parsed.get("invoices", [])
        if not invoices:
            raise ValueError(
                "No invoice could be confidently parsed locally; "
                "administrator review is required."
            )
        return UAEInvoiceExtractionSchema.model_validate(invoices[0])

    def extract_document(self, extracted_content: dict) -> dict:
        """Parse locally and allow only sanitized spreadsheet headings to AI."""
        if not isinstance(extracted_content, dict):
            raise ValueError("Document extraction result must be an object.")

        if not settings.local_extraction_enabled:
            return {
                "document_classification": "unknown",
                "invoices": [],
                "extraction_notes": [
                    "Local extraction is disabled; administrator review is required."
                ],
                "processed_record_count": 0,
                "processing_mode": ProcessingMode.MANUAL_REVIEW_REQUIRED.value,
                "ai_called": False,
                "outbound_privacy_check_passed": None,
                "sensitive_data_transmitted": False,
                "manual_review_required": True,
                "processing_reason": "Local extraction is disabled.",
            }

        parsed = parse_local_invoices(extracted_content)
        ai_called = False
        privacy_gate_passed: bool | None = None
        ai_warnings: list[str] = []
        if (
            not parsed["local_extraction_reliable"]
            and settings.ai_fallback_enabled
            and parsed["mapping_requests"]
        ):
            privacy_context = self._privacy_context(extracted_content)
            ai_mappings: dict[str, dict[str, str]] = {}
            try:
                for sheet_name, original_to_safe in parsed["mapping_requests"].items():
                    safe_columns = list(original_to_safe.values())
                    mapped = map_invoice_columns_with_ai(
                        safe_columns,
                        privacy_context,
                    )
                    reverse_headers = {
                        safe: original
                        for original, safe in original_to_safe.items()
                    }
                    ai_mappings[sheet_name] = {
                        reverse_headers[safe]: target
                        for safe, target in mapped["mappings"].items()
                    }
                    ai_warnings.extend(mapped.get("warnings", []))
                    ai_called = True
                    privacy_gate_passed = True
                if ai_mappings:
                    remapped = parse_local_invoices(
                        extracted_content,
                        ai_mappings=ai_mappings,
                    )
                    if len(remapped["invoices"]) >= len(parsed["invoices"]):
                        parsed = remapped
            except PrivateAIError as exc:
                ai_called = exc.request_attempted
                privacy_gate_passed = True if exc.request_attempted else None
                ai_warnings.append(str(exc))
            except PrivacyViolationError:
                privacy_gate_passed = False
                ai_warnings.append(
                    "Potentially sensitive or unsafe source context was not sent."
                )

        decision = choose_processing_mode(
            local_extraction_reliable=parsed["local_extraction_reliable"],
            sanitized_context_available=bool(
                parsed["mapping_requests"] and settings.ai_fallback_enabled
            ),
        )
        notes = list(dict.fromkeys(
            parsed["extraction_notes"] + ai_warnings
        ))
        if ai_called and parsed["local_extraction_reliable"]:
            mode = ProcessingMode.REDACTED_AI
            reason = "AI interpreted sanitized column headings only."
            manual_review_required = False
        elif not parsed["local_extraction_reliable"]:
            mode = ProcessingMode.MANUAL_REVIEW_REQUIRED
            reason = (
                "Automated interpretation was not safe or reliable. "
                "Administrator review is required."
            )
            manual_review_required = True
        else:
            mode = decision.mode
            reason = decision.reason
            manual_review_required = decision.manual_review_required

        return {
            "document_classification": parsed["document_classification"],
            "invoices": parsed["invoices"],
            "extraction_notes": notes,
            "processed_record_count": parsed["processed_record_count"],
            "processing_mode": mode.value,
            "ai_called": ai_called,
            "outbound_privacy_check_passed": privacy_gate_passed,
            "sensitive_data_transmitted": False,
            "manual_review_required": manual_review_required,
            "processing_reason": reason,
            "parser_version": parsed["parser_version"],
            "worksheet_classifications": parsed["worksheet_classifications"],
            "docx_table_count": parsed.get("docx_table_count"),
            "docx_validation_errors": parsed.get("docx_validation_errors", []),
            "financially_consistent": parsed.get("financially_consistent"),
        }

    @staticmethod
    def _privacy_context(extracted_content: dict) -> PrivacyContext:
        context = PrivacyContext()
        protect_value(extracted_content.get("filename"), "SOURCE_FILENAME", context)
        sensitive_fields = {
            "supplier_name", "supplier_trn", "supplier_address",
            "customer_name", "customer_trn", "customer_address",
            "customer_email", "invoice_number",
        }
        for table in extracted_content.get("tables", []):
            if not isinstance(table, dict):
                continue
            rows = table.get("records")
            columns = table.get("columns")
            if not isinstance(rows, list) or not isinstance(columns, list):
                continue
            mapping = map_columns([str(column) for column in columns])
            for field in sensitive_fields:
                column = mapping["resolved"].get(field)
                if column is None:
                    continue
                for row in rows:
                    if isinstance(row, dict):
                        protect_value(
                            row.get(column),
                            f"PRIVATE_{field.upper()}",
                            context,
                        )
        return context


document_agent = DocumentIntelligenceAgent()
