"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import AuthenticatedPage from "@/components/documents/AuthenticatedPage";
import DocumentDetails from "@/components/documents/DocumentDetails";
import DocumentStatusBadge from "@/components/documents/DocumentStatusBadge";
import InvoiceReview from "@/components/documents/InvoiceReview";
import {
  DocumentDetails as DocumentDetailsRecord,
  getDocument,
  processDocument,
  retryDocument,
} from "@/lib/api";

function DocumentDetailWorkspace() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const documentId = Number(params.id);
  const [document, setDocument] = useState<DocumentDetailsRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!Number.isInteger(documentId) || documentId < 1) {
      return;
    }
    try {
      setDocument(await getDocument(documentId));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load this document.");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  async function process() {
    if (!document) return;
    setWorking(true);
    setError("");
    try {
      const result = document.processing_status === "uploaded"
        ? await processDocument(document.id)
        : await retryDocument(document.id);
      setDocument(result.document);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Document processing failed.";
      await refresh();
      setError(message);
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="document-workspace">
      <header className="document-topbar">
        <Link className="document-brand" href="/documents">
          <span className="document-brand-mark">R</span>
          <span><strong>ReceivAI UAE</strong><small>Document Intelligence</small></span>
        </Link>
        <div className="d-flex align-items-center gap-2">
          {document && <DocumentStatusBadge status={document.processing_status} />}
          <button className="btn btn-light btn-sm" type="button" onClick={() => router.push("/documents")}>
            <i className="bi bi-arrow-left me-2" />All documents
          </button>
        </div>
      </header>

      <div className="document-page-container">
        {!Number.isInteger(documentId) || documentId < 1 ? (
          <div className="alert alert-danger" role="alert">Document ID is invalid.</div>
        ) : loading ? (
          <div className="document-loading">
            <span className="spinner-border spinner-border-sm me-2" />
            Loading document…
          </div>
        ) : error && !document ? (
          <div className="alert alert-danger" role="alert">
            {error}
            <button type="button" className="btn btn-sm btn-outline-danger ms-3" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        ) : document ? (
          <>
            {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}
            {(document.processing_status === "uploaded" ||
              document.processing_status === "processing_failed") && (
              <div className="document-card mb-3 d-flex flex-wrap justify-content-between align-items-center gap-3">
                <div>
                  <h1 className="document-page-title mb-1">
                    {document.processing_status === "uploaded"
                      ? "Process uploaded document"
                      : "Retry document processing"}
                  </h1>
                  <div className="small text-secondary">
                    Processing retains this document record and its private source file.
                  </div>
                </div>
                <button className="btn btn-primary" type="button" onClick={() => void process()} disabled={working}>
                  {working ? (
                    <><span className="spinner-border spinner-border-sm me-2" />Processing…</>
                  ) : (
                    <><i className="bi bi-play-fill me-2" />{document.processing_status === "uploaded" ? "Process document" : "Retry processing"}</>
                  )}
                </button>
              </div>
            )}
            {document.processing_status === "pending_review" ? (
              <InvoiceReview document={document} onUpdated={setDocument} />
            ) : (
              <div className="row g-3">
                <div className="col-12 col-xl-8">
                  <div className="document-card">
                    <h1 className="document-page-title text-break">
                      {document.original_filename}
                    </h1>
                    <p className="text-secondary">
                      Document #{document.id} · {document.processing_status.replaceAll("_", " ")}
                    </p>
                    {document.processing_status === "approved" &&
                      document.invoice_id !== null && (
                        <Link className="btn btn-success" href={`/invoices/${document.invoice_id}`}>
                          <i className="bi bi-receipt me-2" />View approved invoice
                        </Link>
                      )}
                  </div>
                </div>
                <div className="col-12 col-xl-4">
                  <DocumentDetails document={document} />
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>
    </main>
  );
}

export default function DocumentDetailsPage() {
  return (
    <AuthenticatedPage>
      <DocumentDetailWorkspace />
    </AuthenticatedPage>
  );
}
