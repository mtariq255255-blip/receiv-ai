import type { DocumentProcessingStatus } from "@/lib/api";

const statusPresentation: Record<
  string,
  { label: string; className: string; icon: string }
> = {
  uploaded: {
    label: "Uploaded",
    className: "text-bg-secondary",
    icon: "bi-cloud-check",
  },
  processing: {
    label: "Processing",
    className: "text-bg-info",
    icon: "bi-arrow-repeat",
  },
  processing_failed: {
    label: "Processing failed",
    className: "text-bg-danger",
    icon: "bi-exclamation-triangle",
  },
  pending_review: {
    label: "Pending review",
    className: "text-bg-warning",
    icon: "bi-pencil-square",
  },
  approved: {
    label: "Approved",
    className: "text-bg-success",
    icon: "bi-check-circle",
  },
  rejected: {
    label: "Rejected",
    className: "text-bg-dark",
    icon: "bi-x-circle",
  },
};

export default function DocumentStatusBadge({
  status,
}: {
  status: DocumentProcessingStatus;
}) {
  const presentation = statusPresentation[status] ?? {
    label: status.replaceAll("_", " "),
    className: "text-bg-secondary",
    icon: "bi-question-circle",
  };

  return (
    <span className={`badge ${presentation.className} text-capitalize`}>
      <i className={`bi ${presentation.icon} me-1`} aria-hidden="true" />
      {presentation.label}
    </span>
  );
}
