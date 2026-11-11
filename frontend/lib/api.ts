const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "receivai_token";

export type DocumentProcessingStatus =
  | "uploaded"
  | "processing"
  | "processing_failed"
  | "pending_review"
  | "approved"
  | "rejected"
  | (string & {});

export type UAEInvoiceItem = {
  description?: string | null;
  quantity?: string | number | null;
  unit?: string | null;
  unit_price_aed?: string | number | null;
  discount_aed?: string | number | null;
  taxable_value_aed?: string | number | null;
  vat_rate?: string | number | null;
  vat_amount_aed?: string | number | null;
  line_total_aed?: string | number | null;
};

export type UAEInvoice = {
  invoice_number?: string | null;
  supplier_name?: string | null;
  supplier_address?: string | null;
  supplier_emirate?: string | null;
  supplier_trn?: string | null;
  customer_name?: string | null;
  customer_address?: string | null;
  customer_emirate?: string | null;
  customer_email?: string | null;
  customer_trn?: string | null;
  invoice_type?: string | null;
  issue_date?: string | null;
  supply_date?: string | null;
  due_date?: string | null;
  place_of_supply?: string | null;
  currency?: string | null;
  items?: UAEInvoiceItem[];
  subtotal_aed?: string | number | null;
  subtotal_before_discount_aed?: string | number | null;
  discount_aed?: string | number | null;
  vat_amount_aed?: string | number | null;
  total_amount_aed?: string | number | null;
  amount_aed?: string | number | null;
  amount_in_words?: string | null;
  declaration_text?: string | null;
  notes?: string | null;
  [key: string]: unknown;
};

export type ValidationResult = {
  is_valid: boolean;
  review_required: boolean;
  errors: string[];
  warnings: string[];
  checks: Record<string, unknown>;
  calculated_totals: Record<string, string | number | null>;
};

export type DocumentRecord = {
  id: number;
  document_id: number;
  invoice_id: number | null;
  original_filename: string;
  mime_type: string | null;
  file_type: string | null;
  processing_status: DocumentProcessingStatus;
  extraction_notes: string | null;
  uploaded_at: string | null;
};

export type DocumentDetails = DocumentRecord & {
  file_size: number | null;
  extracted_data: Record<string, unknown> | null;
};

export type DocumentListResponse = {
  documents: DocumentRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type DocumentUploadResponse = {
  document_id: number;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: DocumentProcessingStatus;
  uploaded_at: string | null;
  message: string;
};

export type DocumentProcessingResponse = {
  message: string;
  status: DocumentProcessingStatus;
  document: DocumentDetails;
};

export type DocumentRejectionResponse = {
  message: string;
  document_id: number;
  status: DocumentProcessingStatus;
};

export type InvoiceApprovalResponse = {
  message: string;
  invoice_id: number;
  invoice_number: string;
  review_status: string;
  status: string;
  amount_aed: string;
};

export type InvoiceRecord = {
  id: number;
  invoice_number: string;
  customer_name: string;
  customer_email: string | null;
  amount_aed: number | string;
  issue_date: string;
  due_date: string;
  status: string;
  source_type: string;
  review_status: string;
  notes?: string | null;
  supplier_name?: string | null;
  supplier_trn?: string | null;
};

export type DocumentCorrectionPayload = UAEInvoice & {
  invoice_index: number;
};

export type DocumentQuery = {
  status?: DocumentProcessingStatus;
  fileType?: string;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
};

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function saveToken(token: string): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(TOKEN_KEY, token);
  }
}

export function clearToken(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

function notifyUnauthorized(): void {
  if (typeof window !== "undefined") {
    clearToken();
    window.dispatchEvent(new Event("receivai:unauthorized"));
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = true
): Promise<T> {
  const headers = new Headers(options.headers || {});
  const token = getToken();

  if (auth && token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`Unable to reach the ReceivAI API: ${error.message}`);
    }
    throw new Error("Unable to reach the ReceivAI API.");
  }

  const body = await response.json().catch(() => ({}));

  if (response.status === 401 && auth) {
    notifyUnauthorized();
    throw new Error("Your session has expired. Please sign in again.");
  }

  if (!response.ok) {
    const detail = body.detail;
    if (typeof detail === "string") {
      throw new Error(detail);
    }
    if (typeof detail === "object" && detail !== null) {
      const payload = detail as {
        message?: unknown;
        errors?: unknown;
        warnings?: unknown;
      };
      const messages = Array.isArray(payload.errors)
        ? payload.errors.filter(
            (item): item is string => typeof item === "string",
          )
        : [];
      const validationMessages = Array.isArray(detail)
        ? detail.map((item) => {
            if (
              typeof item === "object" &&
              item !== null &&
              "msg" in item &&
              typeof item.msg === "string"
            ) {
              return item.msg;
            }
            return "";
          }).filter(Boolean)
        : [];
      const message =
        typeof payload.message === "string"
          ? payload.message
          : [...messages, ...validationMessages].join(" ");
      if (message) {
        throw new Error(message);
      }
    }
    const statusMessages: Record<number, string> = {
      403: "You do not have permission to perform this action.",
      404: "The requested record could not be found.",
      409: "This action conflicts with the document's current workflow status.",
      413: "The file exceeds the maximum permitted upload size.",
      422: "The submitted data could not be processed. Check the invoice details.",
    };
    throw new Error(
      statusMessages[response.status] || `Request failed (${response.status})`,
    );
  }

  return body as T;
}

export const apiGet = <T,>(path: string) => request<T>(path);

export const apiPost = <T,>(path: string, body: unknown) =>
  request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const apiPut = <T,>(path: string, body: unknown) =>
  request<T>(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const apiPatch = <T,>(path: string, body: unknown) =>
  request<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

export const apiUpload = <T,>(path: string, file: File) => {
  const form = new FormData();
  form.append("file", file);

  return request<T>(path, {
    method: "POST",
    body: form,
  });
};

export function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  return apiUpload<DocumentUploadResponse>("/api/documents/upload", file);
}

export function processDocument(
  documentId: number,
): Promise<DocumentProcessingResponse> {
  return apiPost<DocumentProcessingResponse>(
    `/api/documents/${documentId}/process`,
    {},
  );
}

export function retryDocument(
  documentId: number,
): Promise<DocumentProcessingResponse> {
  return apiPost<DocumentProcessingResponse>(
    `/api/documents/${documentId}/retry`,
    {},
  );
}

export function getDocuments(
  query: DocumentQuery = {},
): Promise<DocumentListResponse> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.fileType) params.set("file_type", query.fileType);
  if (query.search) params.set("search", query.search);
  if (query.dateFrom) params.set("date_from", query.dateFrom);
  if (query.dateTo) params.set("date_to", query.dateTo);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 20));
  return apiGet<DocumentListResponse>(
    `/api/documents/?${params.toString()}`,
  );
}

export function getDocument(documentId: number): Promise<DocumentDetails> {
  return apiGet<DocumentDetails>(`/api/documents/${documentId}`);
}

export async function getDocumentPreview(documentId: number): Promise<Blob> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/api/documents/${documentId}/preview`,
      { headers, cache: "no-store" },
    );
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`Unable to reach the ReceivAI API: ${error.message}`);
    }
    throw new Error("Unable to reach the ReceivAI API.");
  }

  if (response.status === 401) {
    notifyUnauthorized();
    throw new Error("Your session has expired. Please sign in again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as {
      detail?: unknown;
    };
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Unable to load source document (${response.status}).`,
    );
  }

  return response.blob();
}

export function correctDocument(
  documentId: number,
  payload: DocumentCorrectionPayload,
): Promise<DocumentDetails> {
  return apiPut<DocumentDetails>(
    `/api/documents/${documentId}/corrections`,
    payload,
  );
}

export function validateDocument(
  documentId: number,
  payload: DocumentCorrectionPayload,
): Promise<ValidationResult> {
  return apiPost<ValidationResult>(
    `/api/documents/${documentId}/validate`,
    payload,
  );
}

export function approveDocument(
  documentId: number,
  payload: DocumentCorrectionPayload,
): Promise<InvoiceApprovalResponse> {
  return apiPost<InvoiceApprovalResponse>(
    `/api/documents/${documentId}/approve`,
    payload,
  );
}

export function rejectDocument(
  documentId: number,
  reason: string,
): Promise<DocumentRejectionResponse> {
  return apiPost<DocumentRejectionResponse>(
    `/api/documents/${documentId}/reject`,
    { reason },
  );
}

export function getInvoice(invoiceId: number): Promise<InvoiceRecord> {
  return apiGet<InvoiceRecord>(`/api/invoices/${invoiceId}`);
}

export function updateInvoiceStatus(
  invoiceId: number,
  status: "paid" | "unpaid",
): Promise<InvoiceRecord> {
  return apiPatch<InvoiceRecord>(`/api/invoices/${invoiceId}/status`, { status });
}

export type InvoiceCorrection = {
  reason: string;
  invoice_number?: string;
  customer_name?: string;
  customer_email?: string | null;
  supplier_name?: string | null;
  supplier_trn?: string | null;
  issue_date?: string;
  due_date?: string;
  notes?: string | null;
};

export function correctApprovedInvoice(
  invoiceId: number,
  correction: InvoiceCorrection,
): Promise<InvoiceRecord> {
  return apiPatch<InvoiceRecord>(
    `/api/invoices/${invoiceId}/correction`,
    correction,
  );
}

export const login = (email: string, password: string) =>
  request<{
    access_token: string;
    token_type: string;
    expires_in: number;
    admin: { name?: string; email: string };
  }>(
    "/api/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
    false
  );

export const getCurrentAdmin = () =>
  request<{ admin?: { name?: string; email: string } }>(
    "/api/auth/me"
  );
