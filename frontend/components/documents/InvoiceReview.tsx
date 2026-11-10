"use client";

import Link from "next/link";
import { ChangeEvent, useState } from "react";

import DocumentDetails from "@/components/documents/DocumentDetails";
import DocumentStatusBadge from "@/components/documents/DocumentStatusBadge";
import {
  DocumentCorrectionPayload,
  DocumentDetails as DocumentDetailsRecord,
  InvoiceApprovalResponse,
  UAEInvoiceItem,
  ValidationResult,
  approveDocument,
  correctDocument,
  getDocument,
  rejectDocument,
  validateDocument,
} from "@/lib/api";

type ItemDraft = Record<keyof UAEInvoiceItem, string>;
type Draft = {
  invoice_number: string;
  supplier_name: string;
  supplier_address: string;
  supplier_emirate: string;
  supplier_trn: string;
  customer_name: string;
  customer_address: string;
  customer_emirate: string;
  customer_email: string;
  customer_trn: string;
  invoice_type: string;
  issue_date: string;
  supply_date: string;
  due_date: string;
  place_of_supply: string;
  currency: string;
  subtotal_aed: string;
  discount_aed: string;
  vat_amount_aed: string;
  amount_aed: string;
  amount_in_words: string;
  notes: string;
  items: ItemDraft[];
};

type Props = {
  document: DocumentDetailsRecord;
  onUpdated: (document: DocumentDetailsRecord) => void;
};

const emptyItem = (): ItemDraft => ({
  description: "",
  quantity: "",
  unit: "",
  unit_price_aed: "",
  discount_aed: "",
  taxable_value_aed: "",
  vat_rate: "",
  vat_amount_aed: "",
  line_total_aed: "",
});

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function valueString(value: unknown) {
  return value === null || value === undefined ? "" : String(value);
}

function buildDraft(document: DocumentDetailsRecord, index: number): Draft {
  const data = objectValue(document.extracted_data);
  const structured = objectValue(data.structured_invoice);
  const extraction = objectValue(data.structured_extraction);
  const invoices = Array.isArray(extraction.invoices) ? extraction.invoices : [];
  const invoice = index === 0 && Object.keys(structured).length
    ? structured
    : objectValue(invoices[index]);
  const extractedFields = index === 0 ? objectValue(data.fields) : {};
  const reviews = objectValue(data.invoice_reviews);
  const corrected = objectValue(reviews[String(index)]);
  const merged = { ...invoice, ...extractedFields, ...corrected };
  const rawItems = Array.isArray(merged.items) ? merged.items : [];
  return {
    invoice_number: valueString(merged.invoice_number),
    supplier_name: valueString(merged.supplier_name),
    supplier_address: valueString(merged.supplier_address),
    supplier_emirate: valueString(merged.supplier_emirate),
    supplier_trn: valueString(merged.supplier_trn),
    customer_name: valueString(merged.customer_name),
    customer_address: valueString(merged.customer_address),
    customer_emirate: valueString(merged.customer_emirate),
    customer_email: valueString(merged.customer_email),
    customer_trn: valueString(merged.customer_trn),
    invoice_type: valueString(merged.invoice_type),
    issue_date: valueString(merged.issue_date).slice(0, 10),
    supply_date: valueString(merged.supply_date).slice(0, 10),
    due_date: valueString(merged.due_date).slice(0, 10),
    place_of_supply: valueString(merged.place_of_supply),
    currency: valueString(merged.currency),
    subtotal_aed: valueString(merged.subtotal_aed),
    discount_aed: valueString(merged.discount_aed),
    vat_amount_aed: valueString(merged.vat_amount_aed),
    amount_aed: valueString(merged.amount_aed ?? merged.total_amount_aed),
    amount_in_words: valueString(merged.amount_in_words),
    notes: valueString(merged.notes ?? merged.review_notes),
    items: rawItems.map((item) => {
      const row = objectValue(item);
      return {
        description: valueString(row.description),
        quantity: valueString(row.quantity),
        unit: valueString(row.unit),
        unit_price_aed: valueString(row.unit_price_aed),
        discount_aed: valueString(row.discount_aed),
        taxable_value_aed: valueString(row.taxable_value_aed),
        vat_rate: valueString(row.vat_rate),
        vat_amount_aed: valueString(row.vat_amount_aed),
        line_total_aed: valueString(row.line_total_aed),
      };
    }),
  };
}

function toPayload(draft: Draft, invoiceIndex: number): DocumentCorrectionPayload {
  const optional = (value: string) => value.trim() || null;
  return {
    invoice_index: invoiceIndex,
    invoice_number: optional(draft.invoice_number),
    supplier_name: optional(draft.supplier_name),
    supplier_address: optional(draft.supplier_address),
    supplier_emirate: optional(draft.supplier_emirate),
    supplier_trn: optional(draft.supplier_trn),
    customer_name: optional(draft.customer_name),
    customer_address: optional(draft.customer_address),
    customer_emirate: optional(draft.customer_emirate),
    customer_email: optional(draft.customer_email),
    customer_trn: optional(draft.customer_trn),
    issue_date: optional(draft.issue_date),
    supply_date: optional(draft.supply_date),
    due_date: optional(draft.due_date),
    place_of_supply: optional(draft.place_of_supply),
    currency: optional(draft.currency),
    subtotal_aed: optional(draft.subtotal_aed),
    discount_aed: optional(draft.discount_aed),
    vat_amount_aed: optional(draft.vat_amount_aed),
    amount_aed: optional(draft.amount_aed),
    total_amount_aed: optional(draft.amount_aed),
    notes: optional(draft.notes),
    items: draft.items.map((item) => ({
      description: optional(item.description),
      quantity: optional(item.quantity),
      unit: optional(item.unit),
      unit_price_aed: optional(item.unit_price_aed),
      discount_aed: optional(item.discount_aed),
      taxable_value_aed: optional(item.taxable_value_aed),
      vat_rate: optional(item.vat_rate),
      vat_amount_aed: optional(item.vat_amount_aed),
      line_total_aed: optional(item.line_total_aed),
    })),
  };
}

function formatAmount(value: unknown, currency: string) {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return String(value);
  const formatted = amount.toLocaleString("en-AE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${currency.toUpperCase()} ${formatted}` : formatted;
}

function getValidation(document: DocumentDetailsRecord, index: number) {
  const data = objectValue(document.extracted_data);
  const validations = objectValue(data.invoice_validations);
  const stored = objectValue(validations[String(index)]);
  const selected = objectValue(stored.result);
  if (Object.keys(selected).length) return selected as ValidationResult;
  if (index === 0) {
    const legacy = objectValue(data.validation);
    if (Object.keys(legacy).length) return legacy as ValidationResult;
  }
  return null;
}

function statusClass(valid: boolean | null | undefined) {
  if (valid === true) return "text-bg-success";
  if (valid === false) return "text-bg-danger";
  return "text-bg-warning";
}

function ValidationPanel({ result }: { result: ValidationResult | null }) {
  if (!result) {
    return (
      <div className="alert alert-info py-2 small">
        Save or validate the current values to see the latest server-side checks.
      </div>
    );
  }
  const checks = objectValue(result.checks);
  const dates = objectValue(checks.dates);
  const supplierTrn = objectValue(checks.supplier_trn);
  const buyerTrn = objectValue(checks.customer_trn);
  const currency = objectValue(checks.currency);
  const lineItems = objectValue(checks.line_items);
  const vat = objectValue(checks.vat);
  const totals = objectValue(checks.totals);
  const duplicate = objectValue(checks.duplicate);
  const duplicateMatches = Array.isArray(duplicate.matches)
    ? duplicate.matches.map(objectValue)
    : [];
  const ignoredDemoMatches = Array.isArray(duplicate.ignored_demo_matches)
    ? duplicate.ignored_demo_matches.map(objectValue)
    : [];
  const duplicateStatus = String(duplicate.status || "");
  const duplicateBlocksApproval = [
    "same_invoice",
    "conflicting_number",
    "duplicate_upload",
    "duplicate",
    "ambiguous",
  ].includes(duplicateStatus);
  const totalCheck = objectValue(totals.total_amount_aed);
  const checksToShow: { label: string; valid: boolean | null; message: string }[] = [
    {
      label: "Supplier TRN",
      valid: supplierTrn.is_present === true
        ? supplierTrn.is_valid_format === true
        : null,
      message: String(supplierTrn.message || "Not provided"),
    },
    {
      label: "Buyer TRN",
      valid: buyerTrn.is_present === true
        ? buyerTrn.is_valid_format === true
        : null,
      message: String(buyerTrn.message || "Not provided"),
    },
    ...(["issue_date", "supply_date", "due_date"] as const).map((field) => {
      const dateCheck = objectValue(dates[field]);
      return {
        label: field.replace("_", " "),
        valid: typeof dateCheck.is_valid === "boolean" ? dateCheck.is_valid : null,
        message: dateCheck.is_valid === true
          ? "Valid date"
          : dateCheck.is_valid === false
          ? "Invalid calendar date"
          : "Not provided",
      };
    }),
    {
      label: "Currency",
      valid: currency.is_supported_for_aed_ledger === true,
      message: currency.value
        ? `${String(currency.value)} ${currency.is_supported_for_aed_ledger ? "is supported" : "cannot be posted to the AED ledger"}`
        : "Currency is missing",
    },
    {
      label: "Line items",
      valid: typeof lineItems.is_valid === "boolean" ? lineItems.is_valid : null,
      message: `${String(lineItems.count ?? 0)} line item(s) checked`,
    },
    {
      label: "VAT calculation",
      valid: typeof vat.matches === "boolean" ? vat.matches : null,
      message: vat.matches === true
        ? "Calculated VAT matches the extracted value"
        : vat.matches === false
        ? "Calculated VAT differs from the extracted value"
        : "No comparison available",
    },
    {
      label: "Invoice total",
      valid: typeof totalCheck.matches === "boolean" ? totalCheck.matches : null,
      message: totalCheck.matches === true
        ? "Calculated total matches the extracted value"
        : totalCheck.matches === false
        ? "Calculated total differs from the extracted value"
        : "No independent comparison available",
    },
    {
      label: "Duplicate check",
      valid: duplicate.status === "clear"
        ? true
        : duplicateBlocksApproval
        ? false
        : null,
      message: String(duplicate.message || "Not checked"),
    },
  ];
  const totalsResult = objectValue(result.calculated_totals);
  const errors = Array.isArray(result.errors) ? result.errors : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];

  return (
    <section className="document-card mt-3">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div>
          <h3 className="document-subtitle mb-1">Validation results</h3>
          <div className="small text-secondary">
            Official invoice checks and calculations returned by the backend.
          </div>
        </div>
        <span className={`badge ${statusClass(result.is_valid)}`}>
          {result.is_valid ? "Passed" : "Errors found"}
        </span>
      </div>

      <div className="row g-2">
        {checksToShow.map((check) => (
          <div className="col-md-6" key={check.label}>
            <div className="document-check-row">
              <span className={`badge ${statusClass(check.valid)}`}>
                {check.valid === true ? "Pass" : check.valid === false ? "Check" : "Review"}
              </span>
              <div>
                <strong className="text-capitalize">{check.label}</strong>
                <div className="small text-secondary">{check.message}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {duplicateMatches.length > 0 && (
        <div className="small mt-3">
          <strong>Matching records</strong>
          <ul className="mb-0 mt-1">
            {duplicateMatches.map((match, index) => (
              <li key={`${String(match.invoice_id ?? match.document_id)}-${index}`}>
                {match.invoice_id !== undefined
                  ? `Invoice #${String(match.invoice_id)}`
                  : `Document #${String(match.document_id)}`}
                {match.invoice_number ? ` · ${String(match.invoice_number)}` : ""}
                {match.supplier_name ? ` · ${String(match.supplier_name)}` : ""}
                {match.supplier_trn ? ` · TRN ${String(match.supplier_trn)}` : ""}
                {match.filename ? ` · ${String(match.filename)}` : ""}
                {match.source_type ? ` · ${String(match.source_type)}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {ignoredDemoMatches.length > 0 && (
        <div className="small text-secondary mt-3">
          Matching demo records were ignored:
          {" "}
          {ignoredDemoMatches.map((match) => (
            `#${String(match.invoice_id)} (${String(match.invoice_number)})`
          )).join(", ")}
        </div>
      )}

      <div className="document-financial-grid mt-3">
        {[
          ["Calculated subtotal", totalsResult.subtotal_aed],
          ["Calculated discount", totalsResult.discount_aed],
          ["Calculated VAT", totalsResult.vat_amount_aed],
          ["Calculated grand total", totalsResult.total_amount_aed],
        ].map(([label, amount]) => (
          <div className="document-financial-cell" key={String(label)}>
            <span>{String(label)}</span>
            <strong>{formatAmount(amount, "AED")}</strong>
          </div>
        ))}
      </div>

      {errors.length > 0 && (
        <div className="alert alert-danger py-2 small mt-3 mb-2">
          <strong>Items to fix</strong>
          <ul className="mb-0 mt-1">
            {errors.map((error, index) => <li key={index}>{String(error)}</li>)}
          </ul>
        </div>
      )}
      {warnings.length > 0 && (
        <div className="alert alert-warning py-2 small mt-3 mb-0">
          <strong>Warnings</strong>
          <ul className="mb-0 mt-1">
            {warnings.map((warning, index) => <li key={index}>{String(warning)}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}

function TextField({
  label,
  value,
  type = "text",
  required = false,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  type?: string;
  required?: boolean;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const id = `invoice-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="col-md-6">
      <label className="form-label small fw-semibold" htmlFor={id}>{label}</label>
      <input
        id={id}
        className="form-control"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        placeholder={placeholder}
      />
    </div>
  );
}

export default function InvoiceReview({ document, onUpdated }: Props) {
  const data = objectValue(document.extracted_data);
  const extraction = objectValue(data.structured_extraction);
  const invoices = Array.isArray(extraction.invoices) ? extraction.invoices : [];
  const invoiceCount = Math.max(invoices.length, Object.keys(objectValue(data.structured_invoice)).length ? 1 : 0);
  const approvedIndices = Array.isArray(data.approved_invoice_indices)
    ? data.approved_invoice_indices
    : [];
  const firstUnapproved = invoices.findIndex((_, index) => !approvedIndices.includes(index));
  const [invoiceIndex, setInvoiceIndex] = useState(firstUnapproved >= 0 ? firstUnapproved : 0);
  const [draft, setDraft] = useState<Draft>(() => buildDraft(document, invoiceIndex));
  const [validation, setValidation] = useState<ValidationResult | null>(
    () => getValidation(document, invoiceIndex),
  );
  const [busy, setBusy] = useState<"save" | "validate" | "approve" | "reject" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [approval, setApproval] = useState<InvoiceApprovalResponse | null>(null);

  const structuredInvoice = objectValue(data.structured_invoice);
  const originalInvoice =
    invoiceIndex === 0 && Object.keys(structuredInvoice).length
      ? structuredInvoice
      : objectValue(invoices[invoiceIndex]);

  const locked =
    document.processing_status === "approved" ||
    document.processing_status === "rejected" ||
    approvedIndices.includes(invoiceIndex);
  const canEdit = document.processing_status === "pending_review" && !locked;
  const duplicate = objectValue(objectValue(validation?.checks).duplicate);
  const duplicateBlocksApproval = [
    "same_invoice",
    "conflicting_number",
    "duplicate_upload",
    "duplicate",
    "ambiguous",
  ].includes(String(duplicate.status || ""));
  const canApprove =
    canEdit &&
    validation?.is_valid === true &&
    !duplicateBlocksApproval;
  const currencyCode = draft.currency.trim();
  const calculated = objectValue(validation?.calculated_totals);
  const extractedAmount = draft.amount_aed || draft.subtotal_aed;
  const calculatedAmount = calculated.total_amount_aed;
  const extractedAndCalculatedDiffer =
    extractedAmount !== "" &&
    calculatedAmount !== null &&
    calculatedAmount !== undefined &&
    Number(extractedAmount) !== Number(calculatedAmount);

  function setField<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setValidation(null);
    setNotice("");
  }

  function handleItemChange(index: number, field: keyof ItemDraft, value: string) {
    const items = draft.items.map((item, rowIndex) =>
      rowIndex === index ? { ...item, [field]: value } : item,
    );
    setField("items", items);
  }

  async function saveCorrections() {
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const updated = await correctDocument(
        document.id,
        toPayload(draft, invoiceIndex),
      );
      onUpdated(updated);
      const savedValidation = getValidation(updated, invoiceIndex);
      setValidation(savedValidation);
      setNotice("Corrections saved and validation recalculated by the server.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save corrections.");
    } finally {
      setBusy(null);
    }
  }

  async function validateInvoice() {
    setBusy("validate");
    setError("");
    setNotice("");
    try {
      const result = await validateDocument(
        document.id,
        toPayload(draft, invoiceIndex),
      );
      setValidation(result);
      setNotice(result.is_valid
        ? "Validation completed. Review warnings before approval."
        : "Validation found issues that must be resolved before approval.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not validate this invoice.");
    } finally {
      setBusy(null);
    }
  }

  async function approveInvoice() {
    if (!canApprove) return;
    if (!window.confirm(`Approve invoice ${draft.invoice_number || ""} and add it to the invoice register?`)) {
      return;
    }
    setBusy("approve");
    setError("");
    setNotice("");
    try {
      const result = await approveDocument(
        document.id,
        toPayload(draft, invoiceIndex),
      );
      setApproval(result);
      setNotice("Invoice approved and added to the register.");
      try {
        onUpdated(await getDocument(document.id));
      } catch {
        setError("Invoice was approved, but the document status could not be refreshed.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not approve this invoice.");
    } finally {
      setBusy(null);
    }
  }

  async function rejectInvoice() {
    if (!canEdit) return;
    const reason = window.prompt("Enter a reason for rejecting this document:");
    if (!reason?.trim()) return;
    setBusy("reject");
    setError("");
    setNotice("");
    try {
      await rejectDocument(document.id, reason.trim());
      setNotice(`Document rejected. Reason: ${reason.trim()}`);
      try {
        onUpdated(await getDocument(document.id));
      } catch {
        setError("Document was rejected, but its latest status could not be refreshed.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not reject this document.");
    } finally {
      setBusy(null);
    }
  }

  function renderItems() {
    const headers: { key: keyof ItemDraft; label: string; type?: string }[] = [
      { key: "description", label: "Description" },
      { key: "quantity", label: "Qty", type: "number" },
      { key: "unit", label: "Unit" },
      { key: "unit_price_aed", label: "Unit price", type: "number" },
      { key: "discount_aed", label: "Discount", type: "number" },
      { key: "taxable_value_aed", label: "Taxable", type: "number" },
      { key: "vat_rate", label: "VAT %", type: "number" },
      { key: "vat_amount_aed", label: "VAT amount", type: "number" },
      { key: "line_total_aed", label: "Line total", type: "number" },
    ];

    return (
      <div className="table-responsive">
        <table className="table table-sm align-middle document-line-items">
          <thead>
            <tr>
              <th scope="col">#</th>
              {headers.map((header) => <th scope="col" key={header.key}>{header.label}</th>)}
              <th scope="col"><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {draft.items.length === 0 ? (
              <tr><td colSpan={headers.length + 2} className="text-center text-secondary py-4">
                No line items identified. Add a row if the invoice includes line details.
              </td></tr>
            ) : draft.items.map((item, index) => {
              const original = objectValue(
                Array.isArray(originalInvoice.items)
                  ? originalInvoice.items[index]
                  : undefined,
              );
              const lineResult = Array.isArray(objectValue(validation?.checks).line_items &&
                objectValue(objectValue(validation?.checks).line_items).results)
                ? (objectValue(objectValue(validation?.checks).line_items).results as unknown[])[index]
                : undefined;
              const calculatedLine = objectValue(objectValue(lineResult).calculated);
              return (
                <tr key={index}>
                  <th scope="row">{index + 1}</th>
                  {headers.map((header) => {
                    const originalValue = valueString(original[header.key]);
                    const isChanged = originalValue !== "" && originalValue !== item[header.key];
                    return (
                      <td key={header.key}>
                        <input
                          className="form-control form-control-sm document-line-input"
                          type={header.type || "text"}
                          step={header.key === "quantity" ? "0.001" : header.type === "number" ? "0.01" : undefined}
                          value={item[header.key]}
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            handleItemChange(index, header.key, event.target.value)
                          }
                          disabled={!canEdit}
                          aria-label={`Line ${index + 1} ${header.label}`}
                        />
                        {isChanged && (
                          <small className="document-original-value">
                            Extracted: {originalValue}
                          </small>
                        )}
                        {calculatedLine[header.key] !== undefined &&
                          String(calculatedLine[header.key]) !== item[header.key] && (
                            <small className="document-calculated-value">
                              Calculated: {String(calculatedLine[header.key])}
                            </small>
                          )}
                      </td>
                    );
                  })}
                  <td>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-danger"
                      onClick={() => setField("items", draft.items.filter((_, rowIndex) => rowIndex !== index))}
                      disabled={!canEdit}
                      aria-label={`Remove line item ${index + 1}`}
                    >
                      <i className="bi bi-trash" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div>
          <div className="document-kicker">UAE TAX INVOICE REVIEW</div>
          <h1 className="document-page-title mb-1">Review extracted invoice</h1>
          <div className="small text-secondary">
            Confirm the source details, correct extracted values and validate before approval.
          </div>
        </div>
        <DocumentStatusBadge status={document.processing_status} />
      </div>

      {invoiceCount > 1 && (
        <div className="document-card mb-3">
          <label className="form-label fw-semibold" htmlFor="invoice-index-select">
            Invoice in this document
          </label>
          <select
            id="invoice-index-select"
            className="form-select"
            value={invoiceIndex}
            onChange={(event) => {
              const nextIndex = Number(event.target.value);
              setInvoiceIndex(nextIndex);
              setDraft(buildDraft(document, nextIndex));
              setValidation(getValidation(document, nextIndex));
              setApproval(null);
            }}
          >
            {invoices.map((value, index) => {
              const invoice = objectValue(value);
              const isApproved = approvedIndices.includes(index);
              return (
                <option key={index} value={index} disabled={isApproved}>
                  Invoice {index + 1} · {String(invoice.invoice_number || "unnumbered")}
                  {isApproved ? " · approved" : ""}
                </option>
              );
            })}
          </select>
        </div>
      )}

      {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}
      {notice && <div className="alert alert-info py-2" role="status">{notice}</div>}
      {approval && (
        <div className="alert alert-success d-flex flex-wrap justify-content-between align-items-center gap-2">
          <div>
            <strong>Invoice {approval.invoice_number} approved.</strong>
            <div className="small">Created invoice #{approval.invoice_id}.</div>
          </div>
          <Link className="btn btn-sm btn-success" href={`/invoices/${approval.invoice_id}`}>
            View invoice details
          </Link>
        </div>
      )}
      {locked && (
        <div className="alert alert-secondary py-2">
          This invoice is already {document.processing_status}. Corrections and approval are disabled.
        </div>
      )}

      <div className="row g-3 align-items-start">
        <div className="col-xl-4">
          <DocumentDetails document={document} invoiceIndex={invoiceIndex} />
        </div>
        <div className="col-xl-8">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void approveInvoice();
            }}
          >
            <fieldset disabled={!canEdit} className="document-review-fields">
            <div className="document-card">
              <h2 className="document-section-title">Supplier details</h2>
              <div className="row g-3">
                <TextField label="Supplier name" value={draft.supplier_name} required onChange={(value) => setField("supplier_name", value)} />
                <TextField label="Supplier address" value={draft.supplier_address} onChange={(value) => setField("supplier_address", value)} />
                <TextField label="Supplier emirate" value={draft.supplier_emirate} onChange={(value) => setField("supplier_emirate", value)} />
                <TextField label="Supplier TRN" value={draft.supplier_trn} onChange={(value) => setField("supplier_trn", value)} />
              </div>
            </div>

            <div className="document-card mt-3">
              <h2 className="document-section-title">Buyer details</h2>
              <div className="row g-3">
                <TextField label="Buyer name" value={draft.customer_name} required onChange={(value) => setField("customer_name", value)} />
                <TextField label="Buyer email" type="email" value={draft.customer_email} onChange={(value) => setField("customer_email", value)} />
                <TextField label="Buyer address" value={draft.customer_address} onChange={(value) => setField("customer_address", value)} />
                <TextField label="Buyer emirate" value={draft.customer_emirate} onChange={(value) => setField("customer_emirate", value)} />
                <TextField label="Buyer TRN" value={draft.customer_trn} onChange={(value) => setField("customer_trn", value)} />
              </div>
            </div>

            <div className="document-card mt-3">
              <h2 className="document-section-title">Invoice information</h2>
              <div className="row g-3">
                <TextField label="Invoice number" value={draft.invoice_number} required onChange={(value) => setField("invoice_number", value)} />
                <div className="col-md-6">
                  <label className="form-label small fw-semibold" htmlFor="invoice-type">Invoice type</label>
                  <input id="invoice-type" className="form-control" value={draft.invoice_type} readOnly aria-describedby="invoice-type-note" />
                  <small id="invoice-type-note" className="text-secondary">
                    The current document API does not support saving invoice type corrections.
                  </small>
                </div>
                <TextField label="Invoice date" type="date" value={draft.issue_date} required onChange={(value) => setField("issue_date", value)} />
                <TextField label="Supply date" type="date" value={draft.supply_date} onChange={(value) => setField("supply_date", value)} />
                <TextField label="Due date" type="date" value={draft.due_date} required onChange={(value) => setField("due_date", value)} />
                <TextField label="Place of supply" value={draft.place_of_supply} onChange={(value) => setField("place_of_supply", value)} />
                <TextField label="Currency" value={draft.currency} required onChange={(value) => setField("currency", value)} placeholder="Confirm currency; not assumed" />
              </div>
              {!currencyCode && (
                <div className="alert alert-warning py-2 small mt-3 mb-0">
                  Currency was not identified. Confirm it before validation; the application does not assume AED.
                </div>
              )}
            </div>

            <div className="document-card mt-3">
              <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
                <div>
                  <h2 className="document-section-title mb-1">Line items</h2>
                  <div className="small text-secondary">
                    Calculated comparisons appear after server validation.
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => setField("items", [...draft.items, emptyItem()])}
                  disabled={!canEdit}
                >
                  <i className="bi bi-plus-lg me-2" />Add line item
                </button>
              </div>
              {renderItems()}
            </div>

            <div className="document-card mt-3">
              <h2 className="document-section-title">Financial summary</h2>
              <div className="row g-3">
                <TextField label="Extracted subtotal" type="number" value={draft.subtotal_aed} onChange={(value) => setField("subtotal_aed", value)} />
                <TextField label="Extracted discount" type="number" value={draft.discount_aed} onChange={(value) => setField("discount_aed", value)} />
                <TextField label="Extracted VAT amount" type="number" value={draft.vat_amount_aed} onChange={(value) => setField("vat_amount_aed", value)} />
                <TextField label="Extracted grand total" type="number" value={draft.amount_aed} onChange={(value) => setField("amount_aed", value)} />
              </div>
              <div className="document-financial-grid mt-3">
                <div className="document-financial-cell">
                  <span>Extracted taxable base</span>
                  <strong>{formatAmount(draft.subtotal_aed, currencyCode)}</strong>
                </div>
                <div className="document-financial-cell">
                  <span>Calculated taxable base</span>
                  <strong>{validation ? formatAmount(calculated.subtotal_aed, "AED") : "Validate invoice"}</strong>
                </div>
                <div className="document-financial-cell">
                  <span>Calculated discount</span>
                  <strong>{validation ? formatAmount(calculated.discount_aed, "AED") : "Validate invoice"}</strong>
                </div>
                <div className="document-financial-cell">
                  <span>Calculated VAT</span>
                  <strong>{validation ? formatAmount(calculated.vat_amount_aed, "AED") : "Validate invoice"}</strong>
                </div>
                <div className="document-financial-cell">
                  <span>Extracted grand total</span>
                  <strong>{formatAmount(draft.amount_aed, currencyCode)}</strong>
                </div>
                <div className="document-financial-cell">
                  <span>Calculated grand total</span>
                  <strong>{validation ? formatAmount(calculated.total_amount_aed, "AED") : "Validate invoice"}</strong>
                </div>
              </div>
              {extractedAndCalculatedDiffer && (
                <div className="alert alert-warning py-2 small mt-3 mb-0">
                  Extracted and calculated invoice totals differ. Confirm the source values before approval.
                </div>
              )}
              {draft.amount_in_words && (
                <div className="small text-secondary mt-3">
                  <strong>Amount in words:</strong> {draft.amount_in_words}
                </div>
              )}
              <div className="mt-3">
                <label className="form-label small fw-semibold" htmlFor="invoice-review-notes">Review notes</label>
                <textarea
                  id="invoice-review-notes"
                  className="form-control"
                  rows={2}
                  value={draft.notes}
                  onChange={(event) => setField("notes", event.target.value)}
                  disabled={!canEdit}
                />
              </div>
            </div>
            </fieldset>

            <ValidationPanel result={validation} />

            {canEdit && (
              <div className="document-card mt-3">
                <div className="d-flex flex-wrap justify-content-between gap-2">
                  <button
                    type="button"
                    className="btn btn-outline-danger"
                    onClick={() => void rejectInvoice()}
                    disabled={busy !== null}
                  >
                    {busy === "reject" ? "Rejecting…" : "Reject invoice"}
                  </button>
                  <div className="d-flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="btn btn-outline-secondary"
                      onClick={() => void saveCorrections()}
                      disabled={busy !== null}
                    >
                      {busy === "save" ? "Saving…" : "Save corrections"}
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline-primary"
                      onClick={() => void validateInvoice()}
                      disabled={busy !== null}
                    >
                      {busy === "validate" ? "Validating…" : "Validate invoice"}
                    </button>
                    <button
                      type="submit"
                      className="btn btn-success"
                      disabled={!canApprove || busy !== null}
                      title={!canApprove ? "Run a successful validation after the latest edits first" : undefined}
                    >
                      {busy === "approve" ? "Approving…" : "Approve invoice"}
                    </button>
                  </div>
                </div>
                {!canApprove && (
                  <div className="small text-secondary mt-2">
                    Approval is enabled only after the current invoice values pass validation.
                  </div>
                )}
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
