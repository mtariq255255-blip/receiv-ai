"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import DocumentStatusBadge from "@/components/documents/DocumentStatusBadge";
import {
  getDocumentPreview,
  type DocumentDetails as DocumentDetailsRecord,
} from "@/lib/api";

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function readableDate(value: string | null) {
  if (!value) return "Not available";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function detailValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "Not identified";
  }
  return String(value);
}

export default function DocumentDetails({
  document,
  invoiceIndex = 0,
}: {
  document: DocumentDetailsRecord;
  invoiceIndex?: number;
}) {
  const data = objectValue(document.extracted_data);
  const extraction = objectValue(data.structured_extraction);
  const invoices = Array.isArray(extraction.invoices) ? extraction.invoices : [];
  const invoice = Object.keys(objectValue(data.structured_invoice)).length && invoiceIndex === 0
    ? objectValue(data.structured_invoice)
    : objectValue(invoices[invoiceIndex]);
  const metadata = objectValue(
    objectValue(data.raw_extraction).metadata ?? data.processing_metadata,
  );
  const worksheetNames = Array.isArray(metadata.worksheet_names)
    ? metadata.worksheet_names.map(String).join(", ")
    : "";
  const rawExtraction = objectValue(data.raw_extraction);
  const privacy = objectValue(data.privacy_processing);
  const privacyMode = String(privacy.mode || "Not recorded");
  const aiCalled = privacy.ai_called === true;
  const privacyGate = aiCalled
    ? privacy.outbound_privacy_check_passed === true
      ? "Passed"
      : "Failed"
    : privacy.outbound_privacy_check_passed === false
      ? "Failed"
      : "Not applicable";
  const privacyMessage = privacyMode === "LOCAL_ONLY"
    ? "Processed locally. No invoice content was sent to OpenAI."
    : privacyMode === "REDACTED_AI"
      ? "AI interpreted sanitized column headings only."
      : privacyMode === "MANUAL_REVIEW_REQUIRED"
        ? "Automated interpretation was not safe or reliable. Administrator review is required."
        : "Privacy processing details are unavailable for this document.";
  const text = typeof rawExtraction.text === "string"
    ? rawExtraction.text.slice(0, 10000)
    : "";
  const approvals = objectValue(data.approvals);
  const rejection = objectValue(data.rejection);
  const source = [
    invoice.source_page ? `Page ${invoice.source_page}` : null,
    invoice.source_worksheet ? `Worksheet ${invoice.source_worksheet}` : null,
    invoice.source_row ? `Row ${invoice.source_row}` : null,
  ].filter(Boolean);
  const isPdf = document.original_filename.toLowerCase().endsWith(".pdf");
  const [preview, setPreview] = useState<{
    documentId: number;
    url: string;
    error: string;
    loading: boolean;
  }>({ documentId: document.id, url: "", error: "", loading: true });

  useEffect(() => {
    let active = true;
    let objectUrl = "";

    getDocumentPreview(document.id)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPreview({
          documentId: document.id,
          url: objectUrl,
          error: "",
          loading: false,
        });
      })
      .catch((error: unknown) => {
        if (active) {
          setPreview({
            documentId: document.id,
            url: "",
            error: error instanceof Error
              ? error.message
              : "Unable to load source document.",
            loading: false,
          });
        }
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [document.id]);
  const currentPreview = preview.documentId === document.id;
  const previewUrl = currentPreview ? preview.url : "";
  const previewError = currentPreview ? preview.error : "";
  const previewLoading = !currentPreview || preview.loading;

  return (
    <aside className="document-card">
      <div className="d-flex justify-content-between align-items-start gap-2">
        <div>
          <div className="document-kicker">SOURCE DOCUMENT</div>
          <h2 className="document-section-title text-break">
            {document.original_filename}
          </h2>
        </div>
        <DocumentStatusBadge status={document.processing_status} />
      </div>

      <dl className="document-meta-grid mt-3 mb-0">
        <div>
          <dt>Document ID</dt>
          <dd>#{document.id}</dd>
        </div>
        <div>
          <dt>File type</dt>
          <dd className="text-uppercase">{document.file_type || "Unknown"}</dd>
        </div>
        <div>
          <dt>Uploaded</dt>
          <dd>{readableDate(document.uploaded_at)}</dd>
        </div>
        <div>
          <dt>File size</dt>
          <dd>
            {document.file_size !== null
              ? `${(document.file_size / (1024 * 1024)).toFixed(2)} MB`
              : "Not available"}
          </dd>
        </div>
        <div>
          <dt>Extraction</dt>
          <dd>{detailValue(rawExtraction.extraction_method ?? data.processing_status)}</dd>
        </div>
        <div>
          <dt>Source location</dt>
          <dd>{source.length ? source.join(" · ") : "Not provided by extraction"}</dd>
        </div>
      </dl>

      <div className="border-top mt-4 pt-3">
        <h3 className="document-subtitle">Privacy-first processing</h3>
        <p className="small text-secondary mb-2">{privacyMessage}</p>
        <dl className="document-meta-grid mb-0">
          <div>
            <dt>Processing method</dt>
            <dd>{privacyMode}</dd>
          </div>
          <div>
            <dt>AI used</dt>
            <dd>{privacy.ai_called === undefined ? "Not recorded" : aiCalled ? "Yes" : "No"}</dd>
          </div>
          <div>
            <dt>Privacy gate</dt>
            <dd>{privacy.ai_called === undefined ? "Not recorded" : privacyGate}</dd>
          </div>
          <div>
            <dt>Admin review</dt>
            <dd>Required</dd>
          </div>
          {typeof privacy.processing_reason === "string" && (
            <div>
              <dt>Processing reason</dt>
              <dd>{privacy.processing_reason}</dd>
            </div>
          )}
        </dl>
      </div>

      {Object.keys(invoice).length > 0 && (
        <div className="border-top mt-4 pt-3">
          <h3 className="document-subtitle">Original extracted values</h3>
          <dl className="document-meta-grid mb-0">
            {([
              ["Supplier", invoice.supplier_name],
              ["Supplier TRN", invoice.supplier_trn],
              ["Buyer", invoice.customer_name],
              ["Buyer TRN", invoice.customer_trn],
              ["Invoice number", invoice.invoice_number],
              ["Currency", invoice.currency],
              ["Invoice date", invoice.issue_date],
              ["Due date", invoice.due_date],
              ["Subtotal", invoice.subtotal_aed],
              ["Subtotal before discount", invoice.subtotal_before_discount_aed],
              ["VAT amount", invoice.vat_amount_aed],
              ["Grand total", invoice.total_amount_aed],
            ] as const).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{detailValue(value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {document.extraction_notes && (
        <div className="alert alert-warning py-2 small mt-3 mb-0">
          {document.extraction_notes}
        </div>
      )}

      {document.processing_status === "rejected" && (
        <div className="alert alert-danger py-2 small mt-3 mb-0">
          <strong>Rejection reason:</strong>{" "}
          {detailValue(rejection.reason || document.extraction_notes)}
        </div>
      )}

      <div className="border-top mt-4 pt-3">
        <h3 className="document-subtitle">Document preview</h3>
        {previewLoading && (
          <div className="small text-secondary" role="status">Loading original document…</div>
        )}
        {previewError && (
          <div className="alert alert-warning py-2 small" role="alert">{previewError}</div>
        )}
        {previewUrl && (
          <>
            <div className="d-flex justify-content-between align-items-center gap-2 mb-2">
              <p className="small text-secondary mb-0">
                {isPdf
                  ? "Original PDF preview. Use the viewer controls to zoom or navigate pages."
                  : "This file format is not supported by the browser's inline viewer."}
              </p>
              <a
                className="btn btn-sm btn-outline-primary flex-shrink-0"
                href={previewUrl}
                download={document.original_filename}
              >
                <i className="bi bi-download me-1" />Download original
              </a>
            </div>
            {isPdf ? (
              <iframe
                className="document-source-preview"
                src={previewUrl}
                title={`Original source document: ${document.original_filename}`}
              />
            ) : text ? (
              <pre className="document-text-preview">{text}</pre>
            ) : (
              <div className="small text-secondary">
                No inline preview is available for this document type.
              </div>
            )}
          </>
        )}
        {!previewLoading && !previewUrl && text ? (
          <>
            <p className="small text-secondary">
              {previewError
                ? "Showing extracted text because the original file could not be loaded."
                : "Showing extracted text because no original-file preview is available."}
            </p>
            <pre className="document-text-preview">{text}</pre>
          </>
        ) : null}
        {!previewLoading && !previewUrl && !text && (
          <div className="small text-secondary">
            No text preview is available for this document type.
          </div>
        )}
      </div>

      {worksheetNames && (
        <div className="small mt-3">
          <strong>Worksheets:</strong>{" "}
          {worksheetNames}
        </div>
      )}

      {document.invoice_id !== null && (
        <div className="border-top mt-4 pt-3">
          <h3 className="document-subtitle">Approved invoice records</h3>
          <Link className="btn btn-outline-success btn-sm" href={`/invoices/${document.invoice_id}`}>
            <i className="bi bi-box-arrow-up-right me-2" />
            View invoice #{document.invoice_id}
          </Link>
        </div>
      )}
      {Object.entries(approvals)
        .filter(([, value]) => Number(objectValue(value).invoice_id) !== document.invoice_id)
        .map(([index, value]) => {
          const approval = objectValue(value);
          const invoiceId = Number(approval.invoice_id);
          return Number.isInteger(invoiceId) && invoiceId > 0 ? (
            <Link
              className="btn btn-outline-success btn-sm mt-2 me-2"
              href={`/invoices/${invoiceId}`}
              key={index}
            >
              View approved invoice #{invoiceId}
            </Link>
          ) : null;
        })}
    </aside>
  );
}
