"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import AuthenticatedPage from "@/components/documents/AuthenticatedPage";
import DocumentList from "@/components/documents/DocumentList";
import DocumentUpload from "@/components/documents/DocumentUpload";
import WorkspaceSidebar from "@/components/WorkspaceSidebar";
import { clearToken } from "@/lib/api";

function DocumentsWorkspace() {
  const router = useRouter();
  const [refreshKey, setRefreshKey] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const refreshDocuments = useCallback(() => {
    setRefreshKey((current) => current + 1);
  }, []);
  const updatePendingCount = useCallback((count: number) => {
    setPendingCount(count);
  }, []);

  function logout() {
    clearToken();
    router.replace("/");
  }

  return (
    <div className="app-shell">
      <WorkspaceSidebar
        activeView="Document Intelligence"
        pendingCount={pendingCount}
        onLogout={logout}
      />
      <div className="main-area">
        <main className="document-workspace">
      <header className="document-topbar">
        <Link className="document-brand" href="/">
          <span className="document-brand-mark">R</span>
          <span>
            <strong>ReceivAI UAE</strong>
            <small>Finance operations</small>
          </span>
        </Link>
        <nav className="d-flex align-items-center gap-2" aria-label="Workspace navigation">
          <Link className="btn btn-light btn-sm" href="/">
            <i className="bi bi-grid me-2" />Dashboard
          </Link>
          <button className="btn btn-outline-secondary btn-sm" type="button" onClick={logout}>
            <i className="bi bi-box-arrow-right me-2" />Sign out
          </button>
        </nav>
      </header>

      <div className="document-page-container">
        <div className="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
          <div>
            <div className="document-kicker">RECEIVABLES WORKSPACE</div>
            <h1 className="document-page-title">Document Intelligence</h1>
            <p className="text-secondary mb-0">
              Secure invoice intake, UAE tax checks and administrator review.
            </p>
          </div>
          <span className="document-pending-pill">
            <i className="bi bi-inboxes me-2" />
            {pendingCount} pending review
          </span>
        </div>

        <div className="row g-3 mb-4">
          <div className="col-12">
            <DocumentUpload onUploaded={refreshDocuments} />
          </div>
        </div>

        <DocumentList
          refreshKey={refreshKey}
          onPendingReviewCount={updatePendingCount}
        />
      </div>
        </main>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  return (
    <AuthenticatedPage>
      <DocumentsWorkspace />
    </AuthenticatedPage>
  );
}
