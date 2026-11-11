"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import AuthenticatedPage from "@/components/documents/AuthenticatedPage";
import WorkspaceSidebar from "@/components/WorkspaceSidebar";
import {
  clearToken,
  correctApprovedInvoice,
  getInvoice,
  InvoiceCorrection,
  InvoiceRecord,
} from "@/lib/api";

function InvoiceDetailsWorkspace() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const invoiceId = Number(params.id);
  const [invoice, setInvoice] = useState<InvoiceRecord | null>(null);
  const [error, setError] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [savingCorrection, setSavingCorrection] = useState(false);
  const [correctionReason, setCorrectionReason] = useState("");
  const [correctionNotice, setCorrectionNotice] = useState("");
  const [draft, setDraft] = useState<InvoiceCorrection>({
    reason: "",
  });

  function startCorrection() {
    if (!invoice) return;
    setDraft({
      reason: "",
      invoice_number: invoice.invoice_number,
      customer_name: invoice.customer_name,
      customer_email: invoice.customer_email,
      supplier_name: invoice.supplier_name || "",
      supplier_trn: invoice.supplier_trn || "",
      issue_date: invoice.issue_date,
      due_date: invoice.due_date,
      notes: invoice.notes || "",
    });
    setCorrectionReason("");
    setCorrectionNotice("");
    setEditMode(true);
  }

  async function saveCorrection(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!invoice) return;
    setSavingCorrection(true);
    setError("");
    setCorrectionNotice("");
    try {
      const updated = await correctApprovedInvoice(invoice.id, {
        ...draft,
        reason: correctionReason.trim(),
      });
      setInvoice(updated);
      setEditMode(false);
      setCorrectionNotice("Invoice correction saved and recorded in the audit trail.");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not save this correction.");
    } finally {
      setSavingCorrection(false);
    }
  }

  function setField<K extends keyof InvoiceCorrection>(
    key: K,
    value: InvoiceCorrection[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function logout() {
    clearToken();
    router.replace("/");
  }

  useEffect(() => {
    let active = true;
    if (!Number.isInteger(invoiceId) || invoiceId < 1) {
      return () => {
        active = false;
      };
    }
    void getInvoice(invoiceId)
      .then((result) => {
        if (active) setInvoice(result);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Could not load this invoice.");
        }
      });
    return () => {
      active = false;
    };
  }, [invoiceId]);

  return (
    <div className="app-shell">
      <WorkspaceSidebar activeView="Invoice Management" onLogout={logout} />
      <div className="main-area">
        <main className="document-workspace">
      <header className="document-topbar">
        <Link className="document-brand" href="/documents">
          <span className="document-brand-mark">R</span>
          <span><strong>ReceivAI UAE</strong><small>Invoice register</small></span>
        </Link>
        <Link className="btn btn-light btn-sm" href="/documents">
          <i className="bi bi-arrow-left me-2" />Documents
        </Link>
      </header>
      <div className="document-page-container">
        {!Number.isInteger(invoiceId) || invoiceId < 1 ? (
          <div className="alert alert-danger" role="alert">Invoice ID is invalid.</div>
        ) : error ? (
          <div className="alert alert-danger" role="alert">{error}</div>
        ) : !invoice ? (
          <div className="document-loading">
            <span className="spinner-border spinner-border-sm me-2" />Loading invoice…
          </div>
        ) : (
          <article className="document-card">
            <div className="document-kicker">INVOICE #{invoice.id}</div>
            <div className="d-flex flex-wrap justify-content-between align-items-start gap-3">
              <div>
                <h1 className="document-page-title mb-1">{invoice.invoice_number}</h1>
                <div className="text-secondary">{invoice.customer_name}</div>
              </div>
              <div className="d-flex align-items-center gap-2">
                <span className="badge text-bg-success text-capitalize">{invoice.status}</span>
                {!editMode && (
                  <button type="button" className="btn btn-outline-primary btn-sm" onClick={startCorrection}>
                    <i className="bi bi-pencil-square me-2" />Correct invoice
                  </button>
                )}
              </div>
            </div>
            {error && <div className="alert alert-danger py-2 mt-3" role="alert">{error}</div>}
            {correctionNotice && <div className="alert alert-success py-2 mt-3" role="status">{correctionNotice}</div>}
            {editMode && (
              <form className="border rounded p-3 mt-3" onSubmit={(event) => void saveCorrection(event)}>
                <h2 className="document-subtitle">Approved invoice correction</h2>
                <p className="small text-secondary">
                  Changes are saved with a before-and-after audit record. Financial totals and line items are not editable here.
                </p>
                <div className="row g-3">
                  {([
                    ["Invoice number", "invoice_number", "text"],
                    ["Customer name", "customer_name", "text"],
                    ["Customer email", "customer_email", "email"],
                    ["Supplier name", "supplier_name", "text"],
                    ["Supplier TRN", "supplier_trn", "text"],
                    ["Issue date", "issue_date", "date"],
                    ["Due date", "due_date", "date"],
                  ] as const).map(([label, key, type]) => (
                    <div className="col-md-6" key={key}>
                      <label className="form-label small fw-semibold" htmlFor={`correction-${key}`}>{label}</label>
                      <input
                        id={`correction-${key}`}
                        className="form-control"
                        type={type}
                        value={draft[key] || ""}
                        onChange={(event) => setField(key, event.target.value)}
                        required={key === "invoice_number" || key === "customer_name"}
                      />
                    </div>
                  ))}
                  <div className="col-12">
                    <label className="form-label small fw-semibold" htmlFor="correction-notes">Notes</label>
                    <textarea
                      id="correction-notes"
                      className="form-control"
                      rows={3}
                      value={draft.notes || ""}
                      onChange={(event) => setField("notes", event.target.value)}
                    />
                  </div>
                  <div className="col-12">
                    <label className="form-label small fw-semibold" htmlFor="correction-reason">Reason for correction</label>
                    <textarea
                      id="correction-reason"
                      className="form-control"
                      rows={2}
                      value={correctionReason}
                      onChange={(event) => setCorrectionReason(event.target.value)}
                      required
                      maxLength={2000}
                    />
                  </div>
                </div>
                <div className="d-flex justify-content-end gap-2 mt-3">
                  <button type="button" className="btn btn-light" onClick={() => setEditMode(false)} disabled={savingCorrection}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={savingCorrection}>
                    {savingCorrection ? "Saving…" : "Save audited correction"}
                  </button>
                </div>
              </form>
            )}
            <div className="row g-3 mt-2">
              {[
                ["Customer email", invoice.customer_email || "Not provided"],
                ["Amount", `AED ${Number(invoice.amount_aed).toLocaleString("en-AE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`],
                ["Issue date", invoice.issue_date],
                ["Due date", invoice.due_date],
                ["Source document", invoice.source_type],
                ["Review status", invoice.review_status],
              ].map(([label, value]) => (
                <div className="col-12 col-md-6 col-lg-4" key={label}>
                  <div className="document-invoice-property">
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                </div>
              ))}
            </div>
          </article>
        )}
      </div>
        </main>
      </div>
    </div>
  );
}

export default function InvoiceDetailsPage() {
  return (
    <AuthenticatedPage>
      <InvoiceDetailsWorkspace />
    </AuthenticatedPage>
  );
}
