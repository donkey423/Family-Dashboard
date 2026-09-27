const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type DocumentSource = { type: string; availability: string };
export type DocumentRow = { id: string; filename: string; content_type: string; size_bytes: number; created_at: string; revoked_at: string | null; revocation_reason: string | null; sources?: DocumentSource[] };
export type Transaction = { id: string; source_document_id: string; date: string | null; description: string; amount: string; currency: string };
export type TransactionPage = { items: Transaction[]; total: number; limit: number; offset: number };
export type SearchResult = {
  documents: DocumentRow[];
  transactions: Transaction[];
  document_total: number;
  transaction_total: number;
  document_limit: number;
  document_offset: number;
  transaction_limit: number;
  transaction_offset: number;
};
export type Job = { id: string; document_id: string | null; source_type: string; target_module: string; status: string; summary: string; created_at: string };
export type DocumentDetail = {
  document: DocumentRow;
  sources: { type: string; availability: string; has_local_copy: boolean; last_verified_at: string | null }[];
  transactions: Transaction[];
  jobs: Job[];
};
export type CurrencyTotal = { currency: string; income: string; expenses: string; net: string };
export type Dashboard = { transaction_count: number; currency_totals: CurrencyTotal[]; available_currencies: string[] };
export type ImportImpact = Dashboard & { document_id: string; filename: string; revoked_at: string | null; revocation_reason: string | null; impact_token: string };
export type SecretProfile = { id: string; display_name: string; has_credentials: boolean };
export type DocumentSecurityProfile = { id: string; display_name: string; institution: string; sender_pattern: string | null; secret_profile_id: string };
export type GmailStatus = { configured: boolean; authorized: boolean; scope: string | null; last_sync_status: string; last_successful_sync: string | null; last_error_summary: string | null; full_sync_in_progress: boolean; auto_sync_enabled: boolean; next_sync_at: string | null; sync_interval_minutes: number };

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function responseError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  return new ApiError(
    payload?.detail ?? `請求失敗 (${response.status})`,
    response.status,
    response.headers.get("X-FamilyHub-Error"),
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function requestBlob(path: string, body: unknown): Promise<{ blob: Blob; extraction: string | null }> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await responseError(response);
  return { blob: await response.blob(), extraction: response.headers.get("X-FamilyHub-Text-Extraction") };
}

export const api = {
  documentUrl: (id: string) => `${API_BASE}/api/documents/${encodeURIComponent(id)}/content`,
  dashboard: (options: { month?: string; currency?: string } = {}) => {
    const params = new URLSearchParams();
    if (options.month) params.set("month", options.month);
    if (options.currency) params.set("currency", options.currency);
    const query = params.toString();
    return request<Dashboard>(`/api/dashboard${query ? `?${query}` : ""}`);
  },
  documents: (state: "active" | "revoked" | "all" = "active") => request<DocumentRow[]>(`/api/documents?state=${state}`),
  documentDetail: (id: string) => request<DocumentDetail>(`/api/documents/${encodeURIComponent(id)}/detail`),
  importImpact: (id: string) => request<ImportImpact>(`/api/documents/${encodeURIComponent(id)}/import-impact`),
  changeImportState: (id: string, action: "revoke" | "restore", impact_token: string, reason: string) =>
    postJson<ImportImpact & { changed: boolean }>(`/api/documents/${encodeURIComponent(id)}/${action}`, { impact_token, reason }),
  transactions: (options: { limit?: number; offset?: number; month?: string; currency?: string } = {}) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    if (options.month) params.set("month", options.month);
    if (options.currency) params.set("currency", options.currency);
    return request<TransactionPage>(`/api/finance/transactions?${params.toString()}`);
  },
  jobs: () => request<Job[]>("/api/jobs"),
  search: (q: string, options: { documentLimit?: number; documentOffset?: number; transactionLimit?: number; transactionOffset?: number } = {}) => {
    const params = new URLSearchParams({ q });
    if (options.documentLimit !== undefined) params.set("document_limit", String(options.documentLimit));
    if (options.documentOffset !== undefined) params.set("document_offset", String(options.documentOffset));
    if (options.transactionLimit !== undefined) params.set("transaction_limit", String(options.transactionLimit));
    if (options.transactionOffset !== undefined) params.set("transaction_offset", String(options.transactionOffset));
    return request<SearchResult>(`/api/search?${params.toString()}`);
  },
  upload: (file: File, finance: boolean) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ id?: string; document_id?: string; duplicate?: boolean; created_transactions?: number; skipped_revoked?: boolean }>(finance ? "/api/finance/import-csv" : "/api/documents", { method: "POST", body });
  },
  saveLocal: (id: string) => postJson<{ id: string; saved_locally: boolean }>(`/api/documents/${encodeURIComponent(id)}/save-local`, {}),
  preview: (id: string, input: { document_security_profile_id: string; subject: string; body: string; allow_ai_analysis: boolean }) =>
    requestBlob(`/api/documents/${encodeURIComponent(id)}/preview`, input),
  secretProfiles: () => request<SecretProfile[]>("/api/security/profiles"),
  createSecretProfile: (input: { display_name: string; national_id: string; birthday: string }) =>
    postJson<SecretProfile>("/api/security/profiles", input),
  documentSecurityProfiles: () => request<DocumentSecurityProfile[]>("/api/security/document-profiles"),
  createDocumentSecurityProfile: (input: Omit<DocumentSecurityProfile, "id">) =>
    postJson<DocumentSecurityProfile>("/api/security/document-profiles", input),
  aiProvider: () => request<{ configured: boolean; provider: string | null; model: string | null }>("/api/security/ai-provider"),
  configureAiProvider: (input: { api_key: string; model: string }) => postJson<{ configured: boolean; model: string }>("/api/security/ai-provider", input),
  gmailStatus: () => request<GmailStatus>("/api/gmail/status"),
  configureGmail: (config: Record<string, unknown>) => postJson<{ configured: boolean }>("/api/gmail/oauth-client", { config }),
  authorizeGmail: () => postJson<{ authorized: boolean; scope: string }>("/api/gmail/authorize", {}),
  setGmailSchedule: (enabled: boolean) => postJson<{ auto_sync_enabled: boolean; next_sync_at: string | null; sync_interval_minutes: number }>("/api/gmail/schedule", { enabled }),
  syncGmail: () => postJson<{ scanned_messages: number; new_attachments: number; csv_files: number; created_transactions: number; duplicates: number; skipped_revoked: number; failures: number; truncated: number }>("/api/gmail/sync", {}),
};
