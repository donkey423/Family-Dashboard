const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type DocumentSource = { type: string; availability: string };
export type DocumentRow = { id: string; filename: string; content_type: string; size_bytes: number; created_at: string; sources?: DocumentSource[] };
export type Transaction = { id: string; source_document_id: string; date: string | null; description: string; amount: string; currency: string };
export type TransactionPage = { items: Transaction[]; total: number; limit: number; offset: number };
export type Job = { id: string; source_type: string; target_module: string; status: string; summary: string; created_at: string };
export type CurrencyTotal = { currency: string; income: string; expenses: string; net: string };
export type Dashboard = { transaction_count: number; currency_totals: CurrencyTotal[] };
export type SecretProfile = { id: string; display_name: string; has_credentials: boolean };
export type DocumentSecurityProfile = { id: string; display_name: string; institution: string; sender_pattern: string | null; secret_profile_id: string };
export type GmailStatus = { configured: boolean; authorized: boolean; scope: string | null; last_sync_status: string; last_successful_sync: string | null; last_error_summary: string | null; full_sync_in_progress: boolean; auto_sync_enabled: boolean; next_sync_at: string | null; sync_interval_minutes: number };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `請求失敗 (${response.status})`);
  }
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
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `請求失敗 (${response.status})`);
  }
  return { blob: await response.blob(), extraction: response.headers.get("X-FamilyHub-Text-Extraction") };
}

export const api = {
  documentUrl: (id: string) => `${API_BASE}/api/documents/${encodeURIComponent(id)}/content`,
  dashboard: () => request<Dashboard>("/api/dashboard"),
  documents: () => request<DocumentRow[]>("/api/documents"),
  transactions: (options: { limit?: number; offset?: number; month?: string } = {}) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    if (options.month) params.set("month", options.month);
    return request<TransactionPage>(`/api/finance/transactions?${params.toString()}`);
  },
  jobs: () => request<Job[]>("/api/jobs"),
  search: (q: string) => request<{ documents: DocumentRow[]; transactions: Transaction[] }>(`/api/search?q=${encodeURIComponent(q)}`),
  upload: (file: File, finance: boolean) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ id?: string; document_id?: string; duplicate?: boolean; created_transactions?: number }>(finance ? "/api/finance/import-csv" : "/api/documents", { method: "POST", body });
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
  syncGmail: () => postJson<{ scanned_messages: number; new_attachments: number; csv_files: number; created_transactions: number; duplicates: number; failures: number; truncated: number }>("/api/gmail/sync", {}),
};
