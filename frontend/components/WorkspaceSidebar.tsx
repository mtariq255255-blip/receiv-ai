"use client";

import Link from "next/link";

const workspaceViews = [
  { name: "Overview", icon: "bi-grid-1x2-fill" },
  { name: "Invoice Management", icon: "bi-receipt-cutoff" },
  { name: "Payment Collections", icon: "bi-wallet2" },
  { name: "Cash Flow Forecast", icon: "bi-graph-up-arrow" },
  { name: "AI Finance Assistant", icon: "bi-robot" },
];

type Props = {
  activeView: string;
  pendingCount?: number;
  onSelect?: (view: string) => void;
  onLogout?: () => void;
};

export default function WorkspaceSidebar({
  activeView,
  pendingCount = 0,
  onSelect,
  onLogout,
}: Props) {
  const viewLink = (name: string) => `/?view=${encodeURIComponent(name)}`;

  return (
    <aside className="sidebar">
      <Link className="brand text-decoration-none" href="/">
        <div className="brand-logo">
          <i className="bi bi-cpu-fill" />
        </div>
        <div>
          <div className="brand-name">ReceivAI UAE</div>
          <div className="brand-sub">
            Agentic Finance Operations
            <br />
            &amp; Invoice Intelligence
          </div>
        </div>
      </Link>

      <div className="nav-caption">Workspace</div>
      <nav aria-label="Workspace navigation">
        {workspaceViews.map((item) => onSelect ? (
          <button
            key={item.name}
            className={`nav-view ${activeView === item.name ? "active" : ""}`}
            type="button"
            aria-current={activeView === item.name ? "page" : undefined}
            onClick={() => onSelect(item.name)}
          >
            <i className={`bi ${item.icon} nav-icon`} />
            {item.name}
          </button>
        ) : (
          <Link
            key={item.name}
            className={`nav-view ${activeView === item.name ? "active" : ""}`}
            href={viewLink(item.name)}
            aria-current={activeView === item.name ? "page" : undefined}
          >
            <i className={`bi ${item.icon} nav-icon`} />
            {item.name}
          </Link>
        ))}
      </nav>

      <div className="mt-4 nav-caption">Management</div>
      {onSelect ? (
        <>
          <button className="nav-view" type="button" onClick={() => onSelect("Reports")}>
            <i className="bi bi-file-earmark-bar-graph nav-icon" />
            Reports
          </button>
          <Link className="nav-view document-nav-link" href="/documents" aria-current={activeView === "Document Intelligence" ? "page" : undefined}>
            <i className="bi bi-file-earmark-text nav-icon" />
            <span>Document Intelligence</span>
            {pendingCount > 0 && (
              <span className="badge rounded-pill bg-warning text-dark ms-auto">
                {pendingCount}
              </span>
            )}
          </Link>
          <button className="nav-view" type="button" onClick={() => onSelect("Audit Logs")}>
            <i className="bi bi-shield-check nav-icon" />
            Audit Logs
          </button>
        </>
      ) : (
        <>
          <Link className="nav-view" href={viewLink("Reports")}>
            <i className="bi bi-file-earmark-bar-graph nav-icon" />
            Reports
          </Link>
          <Link
            className={`nav-view document-nav-link ${activeView === "Document Intelligence" ? "active" : ""}`}
            href="/documents"
            aria-current={activeView === "Document Intelligence" ? "page" : undefined}
          >
            <i className="bi bi-file-earmark-text nav-icon" />
            <span>Document Intelligence</span>
            {pendingCount > 0 && (
              <span className="badge rounded-pill bg-warning text-dark ms-auto">{pendingCount}</span>
            )}
          </Link>
          <Link className="nav-view" href={viewLink("Audit Logs")}>
            <i className="bi bi-shield-check nav-icon" />
            Audit Logs
          </Link>
        </>
      )}

      <div className="sidebar-bottom">
        <div className="sidebar-foot">
          UAE · AI · Finance
          <br />
          MVP workspace · Administrator
        </div>
        {onLogout && (
          <button className="btn btn-sm btn-outline-light mt-3 w-100" type="button" onClick={onLogout}>
            <i className="bi bi-box-arrow-right me-2" />Sign out
          </button>
        )}
      </div>
    </aside>
  );
}
