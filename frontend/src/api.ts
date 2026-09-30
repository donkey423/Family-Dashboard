const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export type DocumentSource = { type: string; availability: string };
export type DocumentRow = { id: string; filename: string; content_type: string; size_bytes: number; created_at: string; revoked_at: string | null; revocation_reason: string | null; sources?: DocumentSource[] };
export type Transaction = { id: string; source_document_id: string; date: string | null; description: string; amount: string; currency: string; category_id?: string; category_code?: string; category_name?: string; category_source?: string; merchant_key?: string; transaction_kind?: string | null };
export type Category = { id: string; code: string; display_name: string; sort_order: number; is_active: boolean; is_system: boolean };
export type CategoryRule = { id: string; category_id: string; match_type: "normalized_exact" | "contains"; pattern: string; priority: number; enabled: boolean };
export type CategoryTotal = { category_id: string; code: string; name: string; net_amount: string; transaction_count: number };
export type CategorySpending = { month: string | null; currency: string; dashboard_expense: string; positive_category_total: string; refund_credit_total: string; categories: CategoryTotal[]; negative_categories: CategoryTotal[] };
export type CategoryMerchant = { merchant_key: string; display_name: string; transaction_id: string; net_amount: string; transaction_count: number };
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
export type StatementLine = { line_index: number; page_number: number | null; source_sequence: string | null; transaction_date: string | null; effective_transaction_date?: string | null; transaction_date_basis?: "statement" | "statement_closing_date" | "missing"; posting_date: string | null; description: string; transaction_kind: "purchase" | "refund" | "payment" | "fee" | "interest" | "unknown"; amount: string; currency: string };
export type Statement = {
  statement_id: string;
  document_id: string;
  statement_account_id: string | null;
  account_name: string | null;
  bank_id: string;
  format_version: string;
  parser_id: string | null;
  parser_version: string | null;
  period_start: string | null;
  period_end: string | null;
  status: "pending" | "ready" | "imported";
  reason_code: string | null;
  review_version: number;
  line_count: number;
  transaction_count: number;
  reconciliation: { status: "not_checked" | "matched" | "mismatch"; basis: string | null; difference: string | null } | null;
  created_at: string;
  updated_at: string;
  imported_at: string | null;
  lines?: StatementLine[];
};
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
export type PersonalUnlockStatus = { has_national_id: boolean; has_birthday: boolean };
export type AiProvider = "groq" | "openai";
export type AiProviderStatus = { configured: boolean; credential_available: boolean; provider: AiProvider | null; model: string | null };
export type AiProviderTestResult = { ok: true; provider: AiProvider; model: string };
export type CodexMcpStatus = { mode: "codex_mcp"; legacy_gmail_oauth_enabled: boolean; last_import_at: string | null; last_import_status: string | null };

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

export type WorkbookExportStatus = {
  enabled: boolean;
  status: string;
  output_path: string;
  file_available: boolean;
  last_successful_at: string | null;
  last_error: string | null;
  last_error_code: string | null;
  exported_transactions: number;
  current_transactions: number;
  pending_pdf_documents: number;
  needs_update: boolean;
  check_interval_seconds: number;
  pdf_transaction_parser_ready: boolean;
};

async function responseError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;
  const message = typeof detail === "string"
    ? detail
    : typeof detail?.message === "string"
      ? detail.message
      : `請求失敗 (${response.status})`;
  const code = response.headers.get("X-FamilyHub-Error")
    ?? (typeof detail?.code === "string" ? detail.code : null);
  return new ApiError(
    message,
    response.status,
    code,
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

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
  categories: () => request<Category[]>("/api/finance/categories"),
  createCategory: (body: { code: string; display_name: string }) => postJson<Category>("/api/finance/categories", body),
  updateCategory: (id: string, body: Partial<Pick<Category, "display_name" | "is_active" | "sort_order">>) => patchJson<Category>(`/api/finance/categories/${encodeURIComponent(id)}`, body),
  categoryRules: () => request<CategoryRule[]>("/api/finance/category-rules"),
  createCategoryRule: (body: Omit<CategoryRule, "id">) => postJson<CategoryRule>("/api/finance/category-rules", body),
  updateCategoryRule: (id: string, body: Partial<Omit<CategoryRule, "id" | "match_type">>) => patchJson<CategoryRule>(`/api/finance/category-rules/${encodeURIComponent(id)}`, body),
  deleteCategoryRule: (id: string) => request(`/api/finance/category-rules/${encodeURIComponent(id)}`, { method: "DELETE" }),
  spendingByCategory: (month: string, currency: string) => request<CategorySpending>(`/api/finance/spending-by-category?${new URLSearchParams({ month, currency })}`),
  categoryMerchants: (month: string, currency: string, category_id: string) => request<{ items: CategoryMerchant[] }>(`/api/finance/category-merchants?${new URLSearchParams({ month, currency, category_id })}`),
  uncategorizedMerchants: (month: string, currency: string) => request<{ items: CategoryMerchant[] }>(`/api/finance/uncategorized-merchants?${new URLSearchParams({ month, currency })}`),
  assignCategory: (id: string, category_id: string, scope: "transaction" | "merchant") => patchJson<Transaction>(`/api/finance/transactions/${encodeURIComponent(id)}/category`, { category_id, scope }),
  clearCategoryOverride: (id: string) => request<Transaction>(`/api/finance/transactions/${encodeURIComponent(id)}/category`, { method: "DELETE" }),
  workbookStatus: () => request<WorkbookExportStatus>("/api/exports/excel/status"),
  configureWorkbook: (enabled: boolean) => postJson<WorkbookExportStatus>("/api/exports/excel/settings", { enabled }),
  refreshWorkbook: () => postJson<WorkbookExportStatus>("/api/exports/excel/refresh", {}),
  workbookUrl: `${API_BASE}/api/exports/excel/content`,
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
  statements: () => request<Statement[]>('/api/statements'),
  statementDetail: (id: string) => request<Statement>(`/api/statements/${encodeURIComponent(id)}`),
  analyzeStatement: (id: string, input: { allow_ai_analysis?: boolean; subject?: string; body?: string; sender?: string; filename?: string }) =>
    postJson<Statement>(`/api/documents/${encodeURIComponent(id)}/statement-analysis`, input),
  confirmStatement: (id: string, review_version: number) =>
    postJson<{ statement_id: string; document_id: string; status: string; review_version: number; transaction_ids: string[]; transaction_count: number; reused: boolean }>(`/api/statements/${encodeURIComponent(id)}/confirm`, { review_version }),
  importImpact: (id: string) => request<ImportImpact>(`/api/documents/${encodeURIComponent(id)}/import-impact`),
  changeImportState: (id: string, action: "revoke" | "restore", impact_token: string, reason: string) =>
    postJson<ImportImpact & { changed: boolean }>(`/api/documents/${encodeURIComponent(id)}/${action}`, { impact_token, reason }),
  transactions: (options: { limit?: number; offset?: number; month?: string; currency?: string; category_id?: string; merchant_key?: string; consumption_only?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    if (options.category_id) params.set("category_id", options.category_id);
    if (options.merchant_key !== undefined) params.set("merchant_key", options.merchant_key);
    if (options.consumption_only) params.set("consumption_only", "true");
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
  preview: (id: string, input: { subject: string; body: string; allow_ai_analysis: boolean }) =>
    requestBlob(`/api/documents/${encodeURIComponent(id)}/preview`, input),
  personalUnlock: () => request<PersonalUnlockStatus>("/api/security/personal-unlock"),
  savePersonalUnlock: (input: { national_id?: string; birthday?: string }) =>
    request<PersonalUnlockStatus>("/api/security/personal-unlock", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    }),
  secretProfiles: () => request<SecretProfile[]>("/api/security/profiles"),
  createSecretProfile: (input: { display_name: string; national_id: string; birthday: string }) =>
    postJson<SecretProfile>("/api/security/profiles", input),
  documentSecurityProfiles: () => request<DocumentSecurityProfile[]>("/api/security/document-profiles"),
  createDocumentSecurityProfile: (input: Omit<DocumentSecurityProfile, "id">) =>
    postJson<DocumentSecurityProfile>("/api/security/document-profiles", input),
  aiProvider: () => request<AiProviderStatus>("/api/security/ai-provider"),
  testAiProvider: (input: { provider: AiProvider; api_key: string; model: string }) =>
    postJson<AiProviderTestResult>("/api/security/ai-provider/test", input),
  configureAiProvider: (input: { provider: AiProvider; api_key: string; model: string }) =>
    postJson<AiProviderStatus>("/api/security/ai-provider", input),
  codexMcpStatus: () => request<CodexMcpStatus>("/api/integrations/codex-mcp/status"),
};
