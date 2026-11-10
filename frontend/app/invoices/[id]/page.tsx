"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import AuthenticatedPage from "@/components/documents/AuthenticatedPage";
import { getInvoice, InvoiceRecord } from "@/lib/api";

function InvoiceDetailsWorkspace() {
  const params = useParams<{ id: string }>();
  const invoiceId = Number(params.id);
  const [invoice, setInvoice] = useState<InvoiceRecord | null>(null);
  const [error, setError] = useState("");

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
              <span className="badge text-bg-success text-capitalize">{invoice.status}</span>
            </div>
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
  );
}

export default function InvoiceDetailsPage() {
  return (
    <AuthenticatedPage>
      <InvoiceDetailsWorkspace />
    </AuthenticatedPage>
  );
}
