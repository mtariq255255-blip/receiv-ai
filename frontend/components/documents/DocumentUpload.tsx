"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";

import {
  DocumentDetails,
  DocumentUploadResponse,
  getDocument,
  processDocument,
  retryDocument,
  uploadDocument,
} from "@/lib/api";
import DocumentStatusBadge from "@/components/documents/DocumentStatusBadge";

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const FILE_TYPES: Record<string, string> = {
  ".pdf": "PDF",
  ".docx": "DOCX",
  ".xlsx": "XLSX",
  ".xls": "XLS",
  ".csv": "CSV",
};

type Props = {
  onUploaded: () => void | Promise<void>;
};

function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(0)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function DocumentUpload({ onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<DocumentUploadResponse | null>(null);
  const [processedDocument, setProcessedDocument] =
    useState<DocumentDetails | null>(null);
  const [busy, setBusy] = useState<"upload" | "process" | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  function chooseFile(file: File | null) {
    setError("");
    setUpload(null);
    setProcessedDocument(null);
    if (!file) {
      setSelectedFile(null);
      return;
    }

    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!FILE_TYPES[extension]) {
      setSelectedFile(null);
      setError("Choose a PDF, DOCX, XLSX, XLS or CSV document.");
      return;
    }
    if (file.size === 0) {
      setSelectedFile(null);
      setError("The selected file is empty.");
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setSelectedFile(null);
      setError("The maximum upload size is 10 MB.");
      return;
    }
    setSelectedFile(file);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0] ?? null);
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files[0] ?? null);
  }

  async function submitUpload() {
    if (!selectedFile || busy) return;
    setBusy("upload");
    setError("");
    try {
      const result = await uploadDocument(selectedFile);
      setUpload(result);
      setSelectedFile(null);
      await onUploaded();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "The document upload failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function submitProcess() {
    if (!upload || busy) return;
    setBusy("process");
    setError("");
    try {
      const result = upload.status === "processing_failed"
        ? await retryDocument(upload.document_id)
        : await processDocument(upload.document_id);
      setProcessedDocument(result.document);
      setUpload((current) =>
        current ? { ...current, status: result.status } : current,
      );
      await onUploaded();
    } catch (reason) {
      let message =
        reason instanceof Error ? reason.message : "Document processing failed.";
      try {
        const latest = await getDocument(upload.document_id);
        setUpload((current) =>
          current ? { ...current, status: latest.processing_status } : current,
        );
        if (latest.processing_status === "pending_review") {
          setProcessedDocument(latest);
        }
      } catch (refreshError) {
        message = `${message} The latest status could not be confirmed${
          refreshError instanceof Error ? `: ${refreshError.message}` : "."
        }`;
      }
      setError(message);
      await onUploaded();
    } finally {
      setBusy(null);
    }
  }

  const successfulStatus =
    processedDocument?.processing_status ?? upload?.status;
  const extension = selectedFile
    ? selectedFile.name.slice(selectedFile.name.lastIndexOf(".")).toLowerCase()
    : "";

  return (
    <section className="document-card h-100" aria-labelledby="document-upload-title">
      <div className="d-flex align-items-start justify-content-between gap-3 mb-3">
        <div>
          <div className="document-kicker">PRIVATE DOCUMENT INTAKE</div>
          <h2 className="document-section-title" id="document-upload-title">
            Upload an invoice
          </h2>
          <p className="text-secondary small mb-0">
            Files are stored privately. Processing and approval are separate steps.
          </p>
        </div>
        <span className="document-icon"><i className="bi bi-cloud-arrow-up" /></span>
      </div>

      <div
        className={`document-dropzone ${dragging ? "is-dragging" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept=".pdf,.docx,.xlsx,.xls,.csv"
          onChange={handleFileChange}
          aria-label="Choose invoice document"
        />
        <i className="bi bi-file-earmark-arrow-up document-drop-icon" aria-hidden="true" />
        {selectedFile ? (
          <>
            <div className="fw-semibold text-break">{selectedFile.name}</div>
            <div className="small text-secondary mt-1">
              {FILE_TYPES[extension]} · {formatSize(selectedFile.size)}
            </div>
          </>
        ) : (
          <>
            <div className="fw-semibold">Drop a document here</div>
            <div className="small text-secondary mt-1">
              PDF, DOCX, XLSX, XLS or CSV · up to 10 MB
            </div>
          </>
        )}
        <button
          className="btn btn-outline-primary btn-sm mt-3"
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy !== null}
        >
          <i className="bi bi-folder2-open me-2" />
          Browse files
        </button>
      </div>

      {selectedFile && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div className="small text-secondary text-break">
            {selectedFile.name} · {FILE_TYPES[extension]} · {formatSize(selectedFile.size)}
          </div>
          <button
            type="button"
            className="btn btn-link btn-sm text-danger p-0"
            onClick={() => chooseFile(null)}
            disabled={busy !== null}
          >
            Remove file
          </button>
        </div>
      )}

      {error && <div className="alert alert-danger py-2 small mt-3 mb-0" role="alert">{error}</div>}

      {upload && (
        <div className="alert alert-success mt-3 mb-0" role="status">
          <div className="d-flex flex-wrap justify-content-between gap-2">
            <div>
              <strong>Upload confirmed</strong>
              <div className="small mt-1">
                Document #{upload.document_id} · {upload.original_filename}
              </div>
            </div>
            <DocumentStatusBadge status={successfulStatus ?? "uploaded"} />
          </div>
          {processedDocument ? (
            <div className="small mt-2">
              {processedDocument.extraction_notes ||
                "Processing completed. The document is ready for review."}
            </div>
          ) : upload.status === "uploaded" ||
            upload.status === "processing_failed" ? (
            <button
              type="button"
              className="btn btn-sm btn-success mt-3"
              onClick={() => void submitProcess()}
              disabled={busy !== null}
            >
              {busy === "process" ? (
                <><span className="spinner-border spinner-border-sm me-2" />Processing…</>
              ) : (
                <><i className={`bi ${upload.status === "uploaded" ? "bi-play-fill" : "bi-arrow-clockwise"} me-1`} />{upload.status === "uploaded" ? "Process document" : "Retry processing"}</>
              )}
            </button>
          ) : null}
        </div>
      )}

      <div className="d-flex justify-content-end mt-3">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void submitUpload()}
          disabled={!selectedFile || busy !== null}
        >
          {busy === "upload" ? (
            <><span className="spinner-border spinner-border-sm me-2" />Uploading…</>
          ) : (
            <><i className="bi bi-upload me-2" />Upload document</>
          )}
        </button>
      </div>
    </section>
  );
}
