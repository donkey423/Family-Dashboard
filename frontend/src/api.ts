const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type DocumentRow = { id: string; filename: string; content_type: string; size_bytes: number; created_at: string };
export type Transaction = { id: string; source_document_id: string; date: string | null; description: string; amount: string; currency: string };
export type Job = { id: string; source_type: string; target_module: string; status: string; summary: string; created_at: string };
export type CurrencyTotal = { currency: string; income: string; expenses: string; net: string };
export type Dashboard = { transaction_count: number; currency_totals: CurrencyTotal[] };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `請求失敗 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  documentUrl: (id: string) => `${API_BASE}/api/documents/${encodeURIComponent(id)}/content`,
  dashboard: () => request<Dashboard>("/api/dashboard"),
  documents: () => request<DocumentRow[]>("/api/documents"),
  transactions: () => request<Transaction[]>("/api/finance/transactions"),
  jobs: () => request<Job[]>("/api/jobs"),
  search: (q: string) => request<{ documents: DocumentRow[]; transactions: Transaction[] }>(`/api/search?q=${encodeURIComponent(q)}`),
  upload: (file: File, finance: boolean) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ id?: string; document_id?: string; duplicate?: boolean; created_transactions?: number }>(finance ? "/api/finance/import-csv" : "/api/documents", { method: "POST", body });
  },
};
