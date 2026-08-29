// Minimal typed API client. Types are hand-written for Slice 0; a later slice can
// generate them from the backend OpenAPI schema.

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Role = "data_operator" | "reviewer" | "data_consumer";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: Role;
  name: string;
}

const TOKEN_KEY = "loantrust.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export interface FailedRow {
  row_number: number;
  reason: string;
}

export interface UploadSummary {
  id: string;
  filename: string;
  kind: string;
  byte_size: number;
  file_hash: string;
  duplicate: boolean;
  original_upload_id: string | null;
  row_count: number;
  imported_count: number;
  failed_count: number;
  failed_samples: FailedRow[];
  note: string | null;
}

export interface UploadListItem {
  id: string;
  filename: string;
  kind: string;
  row_count: number;
  imported_count: number;
  failed_count: number;
  duplicate: boolean;
  uploaded_at: string;
}

export interface LoanListItem {
  id: string;
  loan_id: string | null;
  borrower_id: string | null;
  payment_status: string | null;
  current_balance: number | null;
  status: string;
  source_file_id: string;
  normalization_status: string;
  issue_fields: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

async function uploadFile(path: string, file: File): Promise<UploadSummary> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  // NOTE: do not set Content-Type — the browser adds the multipart boundary.
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as UploadSummary;
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: string; email: string; name: string; role: Role }>("/auth/me"),
  summary: (role: Role) => {
    const path =
      role === "data_operator"
        ? "/operator/summary"
        : role === "reviewer"
          ? "/reviewer/summary"
          : "/consumer/summary";
    return request<Record<string, unknown>>(path);
  },
  uploadCsv: (file: File, kind = "loan_tape") => uploadFile(`/uploads?kind=${kind}`, file),
  listUploads: () => request<Page<UploadListItem>>("/uploads?limit=50"),
  getUpload: (id: string) => request<UploadSummary>(`/uploads/${id}`),
  listAttentionLoans: () => request<Page<LoanListItem>>("/loans?attention=true&limit=15"),
  validate: (sourceFileId: string) =>
    request<ValidationResult>(`/validate?source_file_id=${sourceFileId}`, { method: "POST" }),

  summaryData: () => request<Summary>("/summary"),

  // Exceptions
  listExceptions: (params: Record<string, string>) =>
    request<Page<ExceptionItem>>(`/exceptions?${new URLSearchParams(params).toString()}`),
  getException: (id: string) => request<ExceptionItem>(`/exceptions/${id}`),
  getLoan: (loanPk: string) => request<LoanDetail>(`/loans/${loanPk}`),
  loanHistory: (loanPk: string) => request<ReviewDecision[]>(`/loans/${loanPk}/history`),
  audit: (loanId: string) => request<AuditEvent[]>(`/audit/${loanId}`),

  // Review actions
  reviewException: (id: string, action: string, expectedVersion: number, comment?: string) =>
    request<{ id: string; status: string; version: number }>(`/exceptions/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ action, expected_version: expectedVersion, comment }),
    }),
  editField: (loanPk: string, field: string, value: string, comment?: string) =>
    request<{ field: string; old: string; new: string }>(`/loans/${loanPk}/fields`, {
      method: "PATCH",
      body: JSON.stringify({ field, value, comment }),
    }),
  loanDecision: (loanPk: string, action: string, comment?: string) =>
    request<{ loan_pk: string; status: string }>(`/loans/${loanPk}/decision`, {
      method: "POST",
      body: JSON.stringify({ action, comment }),
    }),
  addComment: (loanPk: string, comment: string, exceptionId?: string) =>
    request<ReviewDecision>(`/loans/${loanPk}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment, exception_id: exceptionId }),
    }),
  verify: (loanPk: string) =>
    request<{ id: string; version: number; record_hash: string }>(`/loans/${loanPk}/verify`, {
      method: "POST",
    }),

  // AI
  requestAi: (exceptionId: string, kind: string) =>
    request<AIRecommendation>("/ai/request", {
      method: "POST",
      body: JSON.stringify({ exception_id: exceptionId, kind }),
    }),
  listAi: (loanPk: string) => request<AIRecommendation[]>(`/ai/recommendations/${loanPk}`),
  applyAi: (recId: string, disposition: string, overrideValue?: string, comment?: string) =>
    request<{ applied: boolean; disposition: string }>(`/ai/recommendations/${recId}/apply`, {
      method: "POST",
      body: JSON.stringify({ disposition, override_value: overrideValue, comment }),
    }),
  summarizeQueue: () =>
    request<QueueSummary>("/ai/summarize-queue", { method: "POST" }),
  generateNlRule: (naturalLanguage: string) =>
    request<NLRuleResult>("/ai/nl-rule", {
      method: "POST",
      body: JSON.stringify({ natural_language: naturalLanguage }),
    }),

  // Consumer
  listVerified: (q?: string) =>
    request<Page<VerifiedItem>>(`/verified-loans?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  getVerified: (id: string) => request<VerifiedDetail>(`/verified-loans/${id}`),
  trace: (loanPk: string) => request<TraceResult>(`/trace/${loanPk}`),
  exportUrl: (format: string) => `${BASE}/export?format=${format}`,
};

// ---- types for the domain endpoints ----
export interface ValidationResult {
  validation_run_id: string;
  ruleset_version: string;
  loans_evaluated: number;
  totals: Record<string, unknown>;
}
export interface Summary {
  uploads: number;
  loans: number;
  loans_with_exceptions: number;
  open_exceptions: number;
  exceptions_by_severity: Record<string, number>;
  exceptions_by_type: Record<string, number>;
  verified_loans: number;
  data_quality_score: number | null;
  latest_ruleset_version: string | null;
}
export interface ExceptionItem {
  id: string;
  loan_pk: string;
  loan_id: string | null;
  borrower_id: string | null;
  rule_id: string;
  exception_type: string;
  severity: string;
  status: string;
  field: string | null;
  message: string;
  version: number;
  opened_at: string;
  observed_value?: string | null;
}
export interface LoanDetail {
  id: string;
  loan_id: string | null;
  borrower_id: string | null;
  status: string;
  normalization_status: string;
  normalization_notes: Array<Record<string, unknown>> | null;
  field_provenance: Array<Record<string, string>> | null;
  provenance: Record<string, unknown>;
  [k: string]: unknown;
}
export interface ReviewDecision {
  id: string;
  action: string;
  field: string | null;
  old_value: string | null;
  new_value: string | null;
  comment: string | null;
  reviewer_id: string;
  created_at: string;
}
export interface AuditEvent {
  id: string;
  event_type: string;
  actor_role: string | null;
  loan_id: string | null;
  entity_type: string;
  payload: Record<string, unknown> | null;
  occurred_at: string;
}
export interface AIRecommendation {
  id: string;
  loan_pk: string;
  exception_id: string | null;
  kind: string;
  output: Record<string, unknown>;
  suggested_field: string | null;
  suggested_value: string | null;
  degraded: boolean;
  applied: boolean;
  disposition: string | null;
  ai_audit_log_id: string;
  created_at: string;
}
export interface VerifiedItem {
  id: string;
  loan_pk: string;
  loan_id: string | null;
  version: number;
  record_hash: string;
  ai_used: boolean;
  verified_at: string;
}
export interface VerifiedDetail extends VerifiedItem {
  snapshot: Record<string, unknown>;
  validation_summary: Record<string, unknown> | null;
  reviewer_id: string;
  supersedes_version: number | null;
}
export interface QueueSummary {
  stats: {
    total: number;
    by_severity: Record<string, number>;
    top_rules: Array<[string, number]>;
    top_fields: Array<[string, number]>;
    source_conflicts: number;
    affected_loans: number;
  };
  narrative: string;
  priority: string;
  degraded: boolean;
  ai_audit_log_id: string;
}

export interface NLRuleResult {
  output: {
    kind: string;
    natural_language_input: string;
    generated_rules: Array<Record<string, unknown>>;
    explanation: string;
    advisory: boolean;
    note?: string;
  };
  degraded: boolean;
  ai_audit_log_id: string;
}

export interface TraceResult {
  loan_id: string | null;
  source_file: Record<string, unknown> | null;
  raw_record: Record<string, unknown> | null;
  field_provenance: Array<Record<string, string>>;
  validation_results: Array<Record<string, unknown>>;
  exceptions: Array<Record<string, unknown>>;
  ai_recommendations: Array<Record<string, unknown>>;
  review_decisions: Array<Record<string, unknown>>;
  verified_versions: Array<Record<string, unknown>>;
}
