"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import DocumentStatusBadge from "@/components/documents/DocumentStatusBadge";
import {
  DocumentDetails,
  DocumentProcessingStatus,
  DocumentRecord,
  getDocument,
  getDocuments,
  processDocument,
  retryDocument,
} from "@/lib/api";

type Props = {
  refreshKey?: number;
  onPendingReviewCount?: (count: number) => void;
};

const filters: { label: string; value: DocumentProcessingStatus | "" }[] = [
  { label: "All documents", value: "" },
  { label: "Uploaded", value: "uploaded" },
  { label: "Processing", value: "processing" },
  { label: "Pending review", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Processing failed", value: "processing_failed" },
];

type DocumentRow = {
  record: DocumentRecord;
  details: DocumentDetails;
};

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function invoiceValues(details: DocumentDetails) {
  const data = objectValue(details.extracted_data);
  const structured = objectValue(data.structured_invoice);
  const extracted = objectValue(data.structured_extraction);
  const invoices = Array.isArray(extracted.invoices) ? extracted.invoices : [];
  const values = Object.keys(structured).length
    ? structured
    : objectValue(invoices[0]);
  const corrected = objectValue(objectValue(data.invoice_reviews)["0"]);
  return { ...values, ...corrected };
}

function displayDate(value: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
}

export default function DocumentList({
  refreshKey = 0,
  onPendingReviewCount,
}: Props) {
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [totals, setTotals] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [statusFilter, setStatusFilter] =
    useState<DocumentProcessingStatus | "">("");
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workingId, setWorkingId] = useState<number | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, allDocuments, countResults] = await Promise.all([
        getDocuments({
          status: statusFilter || undefined,
          search: search || undefined,
          page,
          pageSize: 20,
        }),
        getDocuments({ page: 1, pageSize: 1 }),
        Promise.all(
          [
            "uploaded",
            "processing",
            "pending_review",
            "approved",
            "rejected",
            "processing_failed",
          ].map(async (status) => {
            const result = await getDocuments({
              status,
              page: 1,
              pageSize: 1,
            });
            return [status, result.total] as const;
          }),
        ),
      ]);
      const nextRows = await Promise.all(
        list.documents.map(async (record) => ({
          record,
          details: await getDocument(record.id),
        })),
      );
      setRows(nextRows);
      setTotal(allDocuments.total);
      setFilteredTotal(list.total);
      setPages(Math.max(1, list.pages));
      const counts = Object.fromEntries(countResults);
      setTotals(counts);
      onPendingReviewCount?.(counts.pending_review ?? 0);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to load documents.",
      );
    } finally {
      setLoading(false);
    }
  }, [onPendingReviewCount, page, search, statusFilter]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDocuments();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadDocuments, refreshKey]);

  const summaryCards = useMemo(
    () => [
      { label: "Total documents", value: total, icon: "bi-files" },
      { label: "Pending review", value: totals.pending_review ?? 0, icon: "bi-pencil-square" },
      { label: "Processing", value: totals.processing ?? 0, icon: "bi-arrow-repeat" },
      { label: "Approved", value: totals.approved ?? 0, icon: "bi-check2-circle" },
      { label: "Failed", value: totals.processing_failed ?? 0, icon: "bi-exclamation-triangle" },
    ],
    [total, totals],
  );

  async function process(record: DocumentRecord) {
    setWorkingId(record.id);
    setError("");
    try {
      if (record.processing_status === "uploaded") {
        await processDocument(record.id);
      } else {
        await retryDocument(record.id);
      }
      await loadDocuments();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Processing failed.";
      await loadDocuments();
      setError(message);
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <section aria-label="Uploaded documents">
      <div className="row g-3 mb-4">
        {summaryCards.map((card) => (
          <div className="col-6 col-xl" key={card.label}>
            <div className="document-stat-card h-100">
              <span className="document-stat-icon"><i className={`bi ${card.icon}`} /></span>
              <div className="document-stat-value">{card.value}</div>
              <div className="document-stat-label">{card.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="document-card">
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-3">
          <div>
            <h2 className="document-section-title mb-1">Documents</h2>
            <div className="small text-secondary">
              Search, process and review uploaded source files.
            </div>
          </div>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => void loadDocuments()}
            disabled={loading}
          >
            <i className={`bi ${loading ? "bi-arrow-repeat" : "bi-arrow-clockwise"} me-2`} />
            Refresh
          </button>
        </div>

        <div className="row g-2 mb-3">
          <div className="col-sm-5 col-lg-3">
            <label className="visually-hidden" htmlFor="document-status-filter">Filter by status</label>
            <select
              id="document-status-filter"
              className="form-select"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value as DocumentProcessingStatus | "");
                setPage(1);
              }}
            >
              {filters.map((filter) => (
                <option key={filter.label} value={filter.value}>{filter.label}</option>
              ))}
            </select>
          </div>
          <form
            className="col-sm-7 col-lg-5 d-flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchText.trim());
              setPage(1);
            }}
          >
            <label className="visually-hidden" htmlFor="document-search">Search filenames</label>
            <input
              id="document-search"
              className="form-control"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search filename"
            />
            <button type="submit" className="btn btn-outline-primary">Search</button>
          </form>
        </div>

        {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}

        {loading ? (
          <div className="document-loading" role="status">
            <span className="spinner-border spinner-border-sm me-2" />
            Loading documents…
          </div>
        ) : rows.length === 0 ? (
          <div className="document-empty">
            <i className="bi bi-folder2-open" aria-hidden="true" />
            <h3>No documents found</h3>
            <p className="mb-0">
              {search || statusFilter
                ? "Try changing the search or status filter."
                : "Upload a PDF, DOCX, XLSX, XLS or CSV invoice to get started."}
            </p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table align-middle document-table">
              <thead>
                <tr>
                  <th scope="col">Filename</th>
                  <th scope="col">File type</th>
                  <th scope="col">Upload date</th>
                  <th scope="col">Processing status</th>
                  <th scope="col">Supplier</th>
                  <th scope="col">Invoice number</th>
                  <th scope="col" className="text-end">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ record, details }) => {
                  const invoice = invoiceValues(details);
                  return (
                    <tr key={record.id}>
                      <td>
                        <Link className="document-filename" href={`/documents/${record.id}`}>
                          {record.original_filename}
                        </Link>
                        <div className="small text-secondary">Document #{record.id}</div>
                      </td>
                      <td className="text-uppercase">{record.file_type || "—"}</td>
                      <td>{displayDate(record.uploaded_at)}</td>
                      <td><DocumentStatusBadge status={record.processing_status} /></td>
                      <td>{String(invoice.supplier_name || "—")}</td>
                      <td>{String(invoice.invoice_number || "—")}</td>
                      <td>
                        <div className="d-flex justify-content-end flex-wrap gap-1">
                          <Link
                            href={`/documents/${record.id}`}
                            className="btn btn-sm btn-outline-secondary"
                            aria-label={`View details for ${record.original_filename}`}
                            title="View details"
                          >
                            <i className="bi bi-eye" />
                          </Link>
                          {(record.processing_status === "uploaded" ||
                            record.processing_status === "processing_failed") && (
                            <button
                              className="btn btn-sm btn-outline-primary"
                              type="button"
                              onClick={() => void process(record)}
                              disabled={workingId === record.id}
                            >
                              {workingId === record.id ? (
                                <span className="spinner-border spinner-border-sm" />
                              ) : (
                                <i className={`bi ${record.processing_status === "uploaded" ? "bi-play-fill" : "bi-arrow-clockwise"}`} />
                              )}
                              <span className="visually-hidden">
                                {record.processing_status === "uploaded" ? "Process" : "Retry"}
                              </span>
                            </button>
                          )}
                          {record.processing_status === "pending_review" && (
                            <Link
                              href={`/documents/${record.id}`}
                              className="btn btn-sm btn-primary"
                            >
                              Review
                            </Link>
                          )}
                          {record.processing_status === "approved" && record.invoice_id !== null && (
                            <Link
                              href={`/invoices/${record.invoice_id}`}
                              className="btn btn-sm btn-outline-success"
                            >
                              View approved invoice
                            </Link>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!loading && total > 0 && (
          <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
            <div className="small text-secondary">
              Page {page} of {pages} · {filteredTotal} document{filteredTotal === 1 ? "" : "s"}
            </div>
            <div className="btn-group" role="group" aria-label="Document list pagination">
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page <= 1}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={() => setPage((current) => Math.min(pages, current + 1))}
                disabled={page >= pages}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
