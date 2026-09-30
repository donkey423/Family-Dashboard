import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type AiProvider, type AiProviderStatus, type CodexMcpStatus, type Dashboard, type DocumentDetail, type DocumentRow, type Job, type Transaction, type PersonalUnlockStatus, type TransactionPage, type ImportImpact, type SearchResult, type Statement } from "./api";
import { ImportLifecycleDialog } from "./ImportLifecycleDialog";
import { useDialogFocus } from "./useDialogFocus";
import { EmptyState } from "./EmptyState";
import { TransactionTable } from "./TransactionTable";
import { ExcelExportSettings } from "./ExcelExportSettings";
import { CategorySettings } from "./categories/CategorySettings";
import { CategoryPicker } from "./categories/CategoryPicker";
import type { Category } from "./api";
import "./categories/categories.css";
const SpendingByCategory = lazy(() => import("./categories/SpendingByCategory").then(module => ({ default: module.SpendingByCategory })));

type View = "overview" | "documents" | "transactions" | "activity" | "settings" | "search";
type SettingsGroup = "connections" | "unlock" | "advanced" | "categories";
type SearchOffsets = { document: number; transaction: number };
type RouteState = { view: View; query: string; searchOffsets: SearchOffsets; month: string; currency: string };
const SEARCH_PAGE_SIZE = 10;
const currentMonth = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
};
const validMonth = (value: string | null) => value && /^\d{4}-\d{2}$/.test(value) ? value : currentMonth();
const monthLabel = (value: string) => {
  const [year, month] = value.split("-");
  return `${year} 年 ${Number(month)} 月`;
};
const viewTitles: Record<View, string> = { overview: "總覽", documents: "文件", transactions: "交易", activity: "匯入紀錄", settings: "設定", search: "搜尋結果" };
const viewDescriptions: Record<View, string> = {
  overview: "掌握已匯入資料與家庭收支。",
  documents: "所有家庭文件的共用資料來源。",
  transactions: "按月份檢視已匯入的收支明細。",
  activity: "查看文件與財務資料的匯入結果。",
  settings: "安全資料、文件解鎖與自動化狀態。",
  search: "從已收錄的文件與有效交易中查找資料。",
};
const settingsGroups: { id: SettingsGroup; label: string; description: string }[] = [
  { id: "unlock", label: "文件解鎖", description: "身分資料與 PDF 密碼" },
  { id: "connections", label: "自動化", description: "Codex MCP 與 Excel" },
  { id: "categories", label: "消費分類", description: "分類與商家規則" },
  { id: "advanced", label: "進階設定", description: "選用的 AI 規則辨識" },
];
function parseOffset(value: string | null) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? Math.floor(parsed / SEARCH_PAGE_SIZE) * SEARCH_PAGE_SIZE : 0;
}
function readRoute(): RouteState {
  const params = new URLSearchParams(window.location.search);
  const candidate = params.get("view");
  const view: View = candidate === "documents" || candidate === "transactions" || candidate === "activity" || candidate === "settings" || candidate === "search" ? candidate : "overview";
  const query = view === "search" ? (params.get("q")?.trim() ?? "") : "";
  return {
    view: view === "search" && !query ? "overview" : view,
    query,
    searchOffsets: { document: parseOffset(params.get("document_offset")), transaction: parseOffset(params.get("transaction_offset")) },
    month: validMonth(params.get("month")),
    currency: params.get("currency")?.trim().toUpperCase() ?? "",
  };
}
function routeUrl(route: RouteState) {
  const params = new URLSearchParams();
  if (route.view !== "overview") params.set("view", route.view);
  if ((route.view === "overview" || route.view === "transactions") && route.month !== currentMonth()) params.set("month", route.month);
  if ((route.view === "overview" || route.view === "transactions") && route.currency) params.set("currency", route.currency);
  if (route.view === "search") {
    params.set("q", route.query);
    if (route.searchOffsets.document > 0) params.set("document_offset", String(route.searchOffsets.document));
    if (route.searchOffsets.transaction > 0) params.set("transaction_offset", String(route.searchOffsets.transaction));
  }
  const search = params.toString();
  return `${window.location.pathname}${search ? `?${search}` : ""}`;
}
const money = (value: string, currency: string) => {
  try { return new Intl.NumberFormat("zh-TW", { style: "currency", currency }).format(Number(value)); }
  catch { return `${currency} ${value}`; }
};
const statementReason = (value: string | null) => {
  const labels: Record<string, string> = {
    parser_not_configured: "帳單解析器尚未啟用。",
    unsupported_bank_layout: "目前尚未支援這份帳單版型。",
    statement_rows_need_ocr: "這份帳單的交易列需要 OCR；目前不會猜測交易。",
    statement_rows_missing: "帳單有應繳金額，但沒有可靠的交易列。",
    statement_reconciliation_mismatch: "交易列合計與帳單金額不一致，未匯入。",
    statement_reconciliation_unavailable: "無法確認帳單合計，未匯入。",
    statement_row_description_unreliable: "交易說明無法可靠讀取，未匯入。",
    statement_row_value_unreliable: "交易日期或金額無法可靠讀取，未匯入。",
    missing_transaction_date: "帳單有明細未列交易日期，已保留解析結果；日期確認前不會入帳。",
  };
  return value?.split(",").map((reason) => labels[reason] ?? reason).join(" ") || "尚未分析。";
};
const statementPeriod = (statement: Statement) => statement.period_start && statement.period_end ? `${statement.period_start} 至 ${statement.period_end}` : "期間待確認";
const groupedMoney = (dashboard: Dashboard, field: "income" | "expenses" | "net") => dashboard.currency_totals.length
  ? dashboard.currency_totals.map((total) => dashboard.currency_totals.length > 1 ? `${total.currency} ${money(total[field], total.currency)}` : money(total[field], total.currency)).join(" · ")
  : "—";

export default function App() {
  const [initialRoute] = useState<RouteState>(() => readRoute());
  const [view, setView] = useState<View>(initialRoute.view);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [periodMonth, setPeriodMonth] = useState(initialRoute.month);
  const [periodCurrency, setPeriodCurrency] = useState(initialRoute.currency);
  const [allDocuments, setDocuments] = useState<DocumentRow[]>([]);
  const documents = useMemo(() => allDocuments.filter((row) => !row.revoked_at), [allDocuments]);
  const revokedDocuments = useMemo(() => allDocuments.filter((row) => row.revoked_at), [allDocuments]);
  const [documentState, setDocumentState] = useState<"active" | "revoked">("active");
  const [lifecycleDocument, setLifecycleDocument] = useState<DocumentRow | null>(null);
  const searchVersion = useRef(0);
  const refreshRequest = useRef(0);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [query, setQuery] = useState(initialRoute.query);
  const [activeSearchQuery, setActiveSearchQuery] = useState(initialRoute.query);
  const [searchOffsets, setSearchOffsets] = useState<SearchOffsets>(initialRoute.searchOffsets);
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [searchLoading, setSearchLoading] = useState(initialRoute.view === "search");
  const [searchError, setSearchError] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewDocument, setPreviewDocument] = useState<DocumentRow | null>(null);
  const [detailDocumentId, setDetailDocumentId] = useState<string | null>(null);
  const [addDataOpen, setAddDataOpen] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);

  const navigate = useCallback((nextView: View, options: { query?: string; searchOffsets?: SearchOffsets; periodMonth?: string; periodCurrency?: string; replace?: boolean } = {}) => {
    const nextQuery = nextView === "search" ? (options.query ?? activeSearchQuery).trim() : "";
    const nextRoute: RouteState = {
      view: nextView === "search" && !nextQuery ? "overview" : nextView,
      query: nextQuery,
      searchOffsets: nextView === "search" ? options.searchOffsets ?? searchOffsets : { document: 0, transaction: 0 },
      month: options.periodMonth ?? periodMonth,
      currency: options.periodCurrency ?? periodCurrency,
    };
    window.history[options.replace ? "replaceState" : "pushState"]({}, "", routeUrl(nextRoute));
    setView(nextRoute.view); setQuery(nextRoute.query); setActiveSearchQuery(nextRoute.query); setSearchOffsets(nextRoute.searchOffsets);
    setPeriodMonth(nextRoute.month); setPeriodCurrency(nextRoute.currency);
    setError("");
    if (nextRoute.view !== "search") { setSearchResult(null); setSearchError(""); }
  }, [activeSearchQuery, periodCurrency, periodMonth, searchOffsets]);

  const refresh = useCallback(async () => {
    const version = ++refreshRequest.current;
    try {
      const [d, docs, tx, j] = await Promise.all([api.dashboard({ month: periodMonth, currency: periodCurrency || undefined }), api.documents("all"), api.transactions({ limit: 8, month: periodMonth, currency: periodCurrency || undefined }), api.jobs()]);
      if (version !== refreshRequest.current) return;
      setDashboard(d); setDocuments(docs); setTransactions(tx.items); setJobs(j); setError("");
      setRefreshVersion((version) => version + 1);
    } catch (reason) {
      if (version === refreshRequest.current) setError(reason instanceof Error ? reason.message : "無法連線至家庭收支記錄服務");
    }
  }, [periodCurrency, periodMonth]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    const onPopState = () => {
      const nextRoute = readRoute();
      setView(nextRoute.view); setQuery(nextRoute.query); setActiveSearchQuery(nextRoute.query); setSearchOffsets(nextRoute.searchOffsets);
      setPeriodMonth(nextRoute.month); setPeriodCurrency(nextRoute.currency);
      setSearchResult(null); setSearchError(""); setError("");
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const changePeriod = useCallback((month: string, currency: string) => {
    navigate(view === "transactions" ? "transactions" : "overview", {
      periodMonth: month,
      periodCurrency: currency,
      replace: true,
    });
  }, [navigate, view]);

  useEffect(() => {
    if (view !== "search" || !activeSearchQuery) {
      setSearchLoading(false); setSearchResult(null); setSearchError("");
      return;
    }
    const version = ++searchVersion.current;
    let active = true;
    setSearchLoading(true); setSearchResult(null); setSearchError("");
    api.search(activeSearchQuery, {
      documentLimit: SEARCH_PAGE_SIZE,
      documentOffset: searchOffsets.document,
      transactionLimit: SEARCH_PAGE_SIZE,
      transactionOffset: searchOffsets.transaction,
    }).then((result) => {
      if (active && version === searchVersion.current) setSearchResult(result);
    }).catch((reason) => {
      if (active && version === searchVersion.current) setSearchError(reason instanceof Error ? reason.message : "搜尋失敗");
    }).finally(() => {
      if (active && version === searchVersion.current) setSearchLoading(false);
    });
    return () => { active = false; };
  }, [activeSearchQuery, searchOffsets, view, refreshVersion]);

  async function upload(file: File | undefined, finance: boolean): Promise<string> {
    if (!file) return "";
    setBusy(true); setMessage(""); setError("");
    try {
      const result = await api.upload(file, finance);
      const messageText = result.skipped_revoked
        ? "這份文件已收錄但目前已撤銷，未新增交易；可到「文件 → 已撤銷」恢復。"
        : finance
          ? result.created_transactions
            ? `CSV 已收錄並建立 ${result.created_transactions} 筆交易`
            : "CSV 已收錄；未新增交易，可能是內容已匯入或沒有可用資料"
          : result.duplicate
            ? "文件已收錄（相同內容沿用既有文件）；尚未建立交易"
            : "文件已收錄；尚未建立交易";
      setMessage(messageText);
      await refresh();
      return messageText;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "匯入失敗");
      throw reason;
    } finally { setBusy(false); }
  }

  function openDocumentDetail(documentId: string) { setDetailDocumentId(documentId); }
  function openLifecycle(document: DocumentRow) { setDetailDocumentId(null); setLifecycleDocument(document); }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    const nextQuery = query.trim();
    if (!nextQuery) { navigate("overview"); return; }
    navigate("search", { query: nextQuery, searchOffsets: { document: 0, transaction: 0 } });
  }

  async function importStateChanged(result: ImportImpact & { changed: boolean }) {
    searchVersion.current += 1;
    navigate("overview", { replace: true }); setLifecycleDocument(null);
    setDocuments((rows) => rows.map((row) => row.id === result.document_id ? { ...row, revoked_at: result.revoked_at, revocation_reason: result.revocation_reason } : row));
    setDashboard(null); setTransactions([]);
    setRefreshVersion((version) => version + 1);
    setMessage(`${result.revoked_at ? "已撤銷" : "已恢復"} ${result.filename}，關聯 ${result.transaction_count} 筆交易`);
    await refresh();
  }

  async function saveLocally(document: DocumentRow) {
    setBusy(true); setMessage(""); setError("");
    try {
      await api.saveLocal(document.id);
      setMessage(`${document.filename} 已保存到本機文件匣`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "無法保存本機副本");
    } finally { setBusy(false); }
  }

  function report(messageText: string, errorText = "") {
    setMessage(messageText); setError(errorText);
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="?view=overview" onClick={(event) => { event.preventDefault(); navigate("overview"); }}><span className="brand-mark">家</span><span>家庭收支記錄</span></a>
      <p className="nav-label">工作區</p>
      <nav aria-label="主要導覽">
        <button className={view === "overview" ? "nav-item active" : "nav-item"} onClick={() => navigate("overview")}><span className="nav-icon">▦</span>總覽</button>
        <button className={view === "documents" ? "nav-item active" : "nav-item"} onClick={() => navigate("documents")}><span className="nav-icon">▤</span>文件</button>
        <button className={view === "transactions" ? "nav-item active" : "nav-item"} onClick={() => navigate("transactions")}><span className="nav-icon">↕</span>交易</button>
        <button className={view === "activity" ? "nav-item active" : "nav-item"} onClick={() => navigate("activity")}><span className="nav-icon">◷</span>匯入紀錄</button>
        <button className={view === "settings" ? "nav-item active" : "nav-item"} onClick={() => navigate("settings")}><span className="nav-icon">⚙</span>設定</button>
      </nav>
      <div className="sidebar-foot"><span className="status-dot" />本機資料庫<span className="local-label">LOCAL</span></div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb">家庭資料 <span>/</span> {viewTitles[view]}</div>
        <form className="search-form" onSubmit={search} role="search"><span aria-hidden="true">⌕</span><input aria-label="搜尋文件與交易" placeholder="搜尋文件與交易" value={query} onChange={(event) => setQuery(event.target.value)} /><button type="submit" title="搜尋" aria-label="搜尋">↵</button></form>
      </header>

      <section className="page-heading">
        <div><p className="eyebrow">家庭資料中心</p><h1>{viewTitles[view]}</h1><p className="subheading">{view === "search" ? `搜尋「${activeSearchQuery}」的文件與交易。` : view === "overview" ? `${monthLabel(periodMonth)} · ${periodCurrency || "全部幣別"}` : viewDescriptions[view]}</p></div>
        {view !== "settings" && <div className="actions">
          {view === "overview" && <div className="period-controls" aria-label="總覽篩選">
            <label>月份<input aria-label="總覽月份" type="month" value={periodMonth} onChange={(event) => changePeriod(event.target.value, periodCurrency)} /></label>
            <label>幣別<select aria-label="總覽幣別" value={periodCurrency || "all"} onChange={(event) => changePeriod(periodMonth, event.target.value === "all" ? "" : event.target.value)}><option value="all">全部幣別</option>{(dashboard?.available_currencies ?? []).map((currency) => <option value={currency} key={currency}>{currency}</option>)}</select></label>
          </div>}
          <button className="button primary" onClick={() => setAddDataOpen(true)}>新增資料</button>
        </div>}
      </section>

      {error && <div className="notice error" role="alert"><span>!</span>{error}<button onClick={() => void refresh()}>重試</button></div>}
      {message && <div className="notice success" role="status"><span>✓</span>{message}<button aria-label="關閉訊息" onClick={() => setMessage("")}>×</button></div>}

      {view === "overview" && <>
        <section className="metrics" aria-label="收支摘要">
          <article className="metric"><div className="metric-top"><span>交易筆數</span><span className="metric-icon green">↗</span></div><strong>{dashboard?.transaction_count ?? "—"}</strong><small>{monthLabel(periodMonth)} · 有效交易</small></article>
          <article className="metric"><div className="metric-top"><span>收入</span><span className="metric-icon blue">＋</span></div><strong className={dashboard && dashboard.currency_totals.length > 1 ? "multi-currency" : undefined}>{dashboard ? groupedMoney(dashboard, "income") : "—"}</strong><small>不同幣別分開計算</small></article>
          <article className="metric"><div className="metric-top"><span>支出</span><span className="metric-icon coral">－</span></div><strong className={dashboard && dashboard.currency_totals.length > 1 ? "multi-currency" : undefined}>{dashboard ? groupedMoney(dashboard, "expenses") : "—"}</strong><small>不同幣別分開計算</small></article>
          <article className="metric"><div className="metric-top"><span>淨額</span><span className="metric-icon lilac">＝</span></div><strong className={dashboard && dashboard.currency_totals.length > 1 ? "multi-currency" : undefined}>{dashboard ? groupedMoney(dashboard, "net") : "—"}</strong><small>收入減去支出</small></article>
        </section>
        <Suspense fallback={<p role="status">載入分類支出…</p>}><SpendingByCategory month={periodMonth} currency={periodCurrency} currencies={dashboard?.available_currencies ?? []} version={refreshVersion} onChanged={refresh} onOpenDocument={openDocumentDetail} /></Suspense>
        <section className="content-grid">
          <div className="panel transactions-panel">
            <div className="panel-heading"><div><h2>期間交易</h2><p>{monthLabel(periodMonth)} · {periodCurrency || "全部幣別"}</p></div><button className="text-button" onClick={() => navigate("transactions", { periodMonth, periodCurrency })}>查看全部交易 <span>→</span></button></div>
            <TransactionTable rows={transactions} onOpenDocument={openDocumentDetail} emptyTitle={`${monthLabel(periodMonth)}尚無交易`} emptyDetail="可切換月份或匯入通用 CSV；不同幣別不會互相加總。" />
          </div>
          <div className="panel documents-panel">
            <div className="panel-heading"><div><h2>最近文件</h2><p>共 {documents.length} 份文件</p></div><button className="icon-button" title="查看所有文件" aria-label="查看所有文件" onClick={() => navigate("documents")}>→</button></div>
          <DocumentList rows={documents.slice(0, 5)} onDetail={openDocumentDetail} onPreview={setPreviewDocument} onSaveLocal={saveLocally} onChangeImport={openLifecycle} busy={busy} />
          </div>
        </section>
         <section className="panel jobs-panel"><div className="panel-heading"><div><h2>最近匯入</h2><p>文件與財務匯入處理狀態</p></div><button className="text-button" onClick={() => navigate("activity")}>全部紀錄 <span>→</span></button></div><JobList rows={jobs.slice(0, 4)} onOpenDocument={openDocumentDetail} /></section>
      </>}

      {view === "search" && <SearchResults query={activeSearchQuery} result={searchResult} loading={searchLoading} error={searchError} offsets={searchOffsets} onClear={() => navigate("overview")} onDocumentPage={(offset) => navigate("search", { searchOffsets: { ...searchOffsets, document: offset } })} onTransactionPage={(offset) => navigate("search", { searchOffsets: { ...searchOffsets, transaction: offset } })} onOpenDocument={openDocumentDetail} onPreview={setPreviewDocument} onSaveLocal={saveLocally} onChangeImport={openLifecycle} busy={busy} />}

      {view === "documents" && <section className="panel page-panel"><div className="panel-heading document-heading"><h2>文件匣</h2><div className="document-state-filter" role="group" aria-label="文件狀態">
        <button aria-pressed={documentState === "active"} onClick={() => setDocumentState("active")}>有效 <span>{documents.length}</span></button>
        <button aria-pressed={documentState === "revoked"} onClick={() => setDocumentState("revoked")}>已撤銷 <span>{revokedDocuments.length}</span></button>
      </div></div><DocumentList rows={documentState === "active" ? documents : revokedDocuments} expanded revoked={documentState === "revoked"} onDetail={openDocumentDetail} onPreview={setPreviewDocument} onSaveLocal={saveLocally} onChangeImport={openLifecycle} busy={busy} /></section>}
      {view === "transactions" && <TransactionsView refreshVersion={refreshVersion} month={periodMonth} currency={periodCurrency} currencies={dashboard?.available_currencies ?? []} onPeriodChange={changePeriod} onOpenDocument={openDocumentDetail} />}
      {view === "activity" && <section className="panel page-panel"><div className="panel-heading"><div><h2>工作與匯入歷史</h2><p>最新 100 筆處理紀錄</p></div></div><JobList rows={jobs} expanded onOpenDocument={openDocumentDetail} /></section>}
      {view === "settings" && <SettingsView report={report} />}
      <footer className="page-footer"><span>家庭收支記錄 v0.1</span><span>資料保存在此 Windows 主機</span></footer>
    </main>
    {addDataOpen && <AddDataDialog busy={busy} onClose={() => setAddDataOpen(false)} onUpload={upload} onSettings={() => { setAddDataOpen(false); navigate("settings"); }} />}
    {detailDocumentId && <DocumentDetailDialog documentId={detailDocumentId} onClose={() => setDetailDocumentId(null)} onPreview={(document) => { setDetailDocumentId(null); setPreviewDocument(document); }} onSaveLocal={saveLocally} onChangeImport={openLifecycle} onImported={refresh} />}
    {previewDocument && <PdfPreviewDialog document={previewDocument} onClose={() => setPreviewDocument(null)} />}
    {lifecycleDocument && <ImportLifecycleDialog document={lifecycleDocument} onClose={() => { setLifecycleDocument(null); void refresh(); }} onChanged={importStateChanged} />}
  </div>;
}

function SearchResults({ query, result, loading, error, offsets, onClear, onDocumentPage, onTransactionPage, onOpenDocument, onPreview, onSaveLocal, onChangeImport, busy }: {
  query: string;
  result: SearchResult | null;
  loading: boolean;
  error: string;
  offsets: SearchOffsets;
  onClear: () => void;
  onDocumentPage: (offset: number) => void;
  onTransactionPage: (offset: number) => void;
  onOpenDocument: (documentId: string) => void;
  onPreview: (document: DocumentRow) => void;
  onSaveLocal: (document: DocumentRow) => void;
  onChangeImport: (document: DocumentRow) => void;
  busy: boolean;
}) {
  const documentTotal = result?.document_total ?? 0;
  const transactionTotal = result?.transaction_total ?? 0;
  return <section className="search-page">
    <div className="panel search-summary">
      <div className="panel-heading"><div><h2>搜尋結果</h2><p>文件與有效交易分開顯示，共 {documentTotal} 份文件、{transactionTotal} 筆交易。</p></div><button className="text-button" onClick={onClear}>清除搜尋</button></div>
    </div>
    {loading && <p className="transaction-loading" role="status">正在搜尋「{query}」…</p>}
    {error && <div className="notice error" role="alert">{error}</div>}
    {!loading && !error && <section className="content-grid search-results-grid">
      <div className="panel transactions-panel">
        <div className="panel-heading"><div><h2>交易</h2><p>符合描述或金額的有效交易</p></div></div>
        <TransactionTable rows={result?.transactions ?? []} onOpenDocument={onOpenDocument} />
        <SearchPagination label="交易搜尋分頁" total={transactionTotal} offset={offsets.transaction} limit={result?.transaction_limit ?? SEARCH_PAGE_SIZE} loading={loading} onPage={onTransactionPage} />
      </div>
      <div className="panel documents-panel">
        <div className="panel-heading"><div><h2>文件</h2><p>符合檔名的有效文件</p></div></div>
        <DocumentList rows={result?.documents ?? []} onDetail={onOpenDocument} onPreview={onPreview} onSaveLocal={onSaveLocal} onChangeImport={onChangeImport} busy={busy} />
        <SearchPagination label="文件搜尋分頁" total={documentTotal} offset={offsets.document} limit={result?.document_limit ?? SEARCH_PAGE_SIZE} loading={loading} onPage={onDocumentPage} />
      </div>
    </section>}
  </section>;
}

function SearchPagination({ label, total, offset, limit, loading, onPage }: { label: string; total: number; offset: number; limit: number; loading: boolean; onPage: (offset: number) => void }) {
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const page = total ? Math.floor(offset / limit) + 1 : 0;
  return <div className="pagination" aria-label={label}>
    <span>{total ? `${page} / ${pageCount} 頁，共 ${total} 筆` : "0 筆"}</span>
    <div>
      <button className="small-action" disabled={offset === 0 || loading} onClick={() => onPage(Math.max(0, offset - limit))}>上一頁</button>
      <button className="small-action" disabled={offset + limit >= total || loading} onClick={() => onPage(offset + limit)}>下一頁</button>
    </div>
  </div>;
}

function TransactionsView({ refreshVersion, month, currency, currencies, onPeriodChange, onOpenDocument }: { refreshVersion: number; month: string; currency: string; currencies: string[]; onPeriodChange: (month: string, currency: string) => void; onOpenDocument: (documentId: string) => void }) {
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState(() => new URLSearchParams(window.location.search).get("category") ?? "");
  const [revision, setRevision] = useState(0);
  useEffect(() => { let active = true; api.categories().then(value => { if (active) setCategories(value); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法載入分類"); }); return () => { active = false; }; }, []);
  useEffect(() => { const listener = () => setCategoryId(new URLSearchParams(window.location.search).get("category") ?? ""); window.addEventListener("popstate", listener); return () => window.removeEventListener("popstate", listener); }, []);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<TransactionPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const pageSize = 50;

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.transactions({ limit: pageSize, offset: page * pageSize, month: month || undefined, currency: currency || undefined, category_id: categoryId || undefined })
      .then((response) => { if (active) { setResult(response); setError(""); } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "無法載入交易"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currency, month, page, refreshVersion, categoryId, revision]);

  useEffect(() => { setPage(0); }, [currency, month, categoryId]);

  const pageCount = Math.max(1, Math.ceil((result?.total ?? 0) / pageSize));
  return <section className="panel page-panel transactions-page">
    <div className="panel-heading"><div><h2>收支明細</h2><p>{monthLabel(month)} · {currency || "全部幣別"} · 共 {result?.total ?? "—"} 筆交易</p></div>
      <div className="transaction-filters"><label className="month-filter">月份<input aria-label="依月份篩選交易" type="month" value={month} onChange={(event) => onPeriodChange(event.target.value, currency)} /></label><label className="month-filter">幣別<select aria-label="依幣別篩選交易" value={currency || "all"} onChange={(event) => onPeriodChange(month, event.target.value === "all" ? "" : event.target.value)}><option value="all">全部幣別</option>{currencies.map((option) => <option value={option} key={option}>{option}</option>)}</select></label></div>
    </div>
    {error && <div className="notice error" role="alert">{error}</div>}
    {loading && <p className="transaction-loading" role="status">正在載入交易…</p>}
    <label className="category-filter">分類<select aria-label="交易分類篩選" value={categoryId} onChange={event => { const value = event.target.value; setCategoryId(value); const url = new URL(window.location.href); if (value) url.searchParams.set("category", value); else url.searchParams.delete("category"); window.history.pushState({}, "", url.pathname + url.search); }}><option value="">全部分類</option>{categories.filter(item => item.is_active).map(item => <option value={item.id} key={item.id}>{item.display_name}</option>)}</select></label>
    {!loading && !error && <TransactionTable rows={result?.items ?? []} onCategory={setSelected} onOpenDocument={onOpenDocument} emptyTitle={`${monthLabel(month)}尚無交易`} emptyDetail="目前沒有符合月份與幣別的有效交易。" />}
    {selected && <CategoryPicker transaction={selected} categories={categories} onClose={() => setSelected(null)} onChanged={() => setRevision(value => value + 1)} />}
    <div className="pagination" aria-label="交易分頁">
      <span>{result?.total ? `${page + 1} / ${pageCount} 頁` : "0 筆交易"}</span>
      <div><button className="small-action" disabled={page === 0 || loading} onClick={() => setPage((current) => Math.max(0, current - 1))}>上一頁</button><button className="small-action" disabled={(page + 1) * pageSize >= (result?.total ?? 0) || loading} onClick={() => setPage((current) => current + 1)}>下一頁</button></div>
    </div>
  </section>;
}

function DocumentList({ rows, expanded = false, revoked = false, onDetail, onPreview, onSaveLocal, onChangeImport, busy = false }: { rows: DocumentRow[]; expanded?: boolean; revoked?: boolean; onDetail?: (documentId: string) => void; onPreview?: (document: DocumentRow) => void; onSaveLocal?: (document: DocumentRow) => void; onChangeImport?: (document: DocumentRow) => void; busy?: boolean }) {
  if (!rows.length) return <EmptyState title={revoked ? "沒有已撤銷的文件" : "文件匣目前是空的"} detail={revoked ? "" : "加入 PDF、JPG、PNG 或 CSV 文件開始整理。"} />;
  return <ul className={expanded ? "document-list expanded" : "document-list"}>{rows.map((row) => {
    const isPdf = row.content_type.includes("pdf") || row.filename.toLowerCase().endsWith(".pdf");
    const hasLocal = row.sources?.some((source) => source.type === "local_file");
    const hasRemote = row.sources?.some((source) => source.type === "gmail_attachment");
    const hasGmail = row.sources?.some((source) => source.type === "gmail_attachment" || source.type === "codex_mcp_gmail");
    const stateLabel = hasLocal ? "本機副本" : hasRemote ? "僅遠端來源" : "本機";
    return <li key={row.id}><span className={`file-icon ${isPdf ? "pdf" : row.content_type.includes("image") ? "image" : "csv"}`}>{isPdf ? "PDF" : row.content_type.includes("image") ? "IMG" : "CSV"}</span><span className="file-info"><a href={api.documentUrl(row.id)} target="_blank" rel="noreferrer"><strong>{row.filename}</strong></a><small>{formatBytes(row.size_bytes)} · {new Date(row.created_at).toLocaleDateString("zh-TW")}{hasGmail ? " · Gmail" : ""}</small>{row.revoked_at && <small className="revocation-detail">已撤銷 · {new Date(row.revoked_at).toLocaleDateString("zh-TW")}{row.revocation_reason ? ` · ${row.revocation_reason}` : ""}</small>}</span><span className="document-actions">{onDetail && <button className="small-action" aria-label={`查看 ${row.filename} 詳情`} onClick={() => onDetail(row.id)}>詳情</button>}{isPdf && onPreview && <button className="small-action" title="開啟 PDF 預覽" aria-label={`預覽 ${row.filename}`} onClick={() => onPreview(row)}>預覽</button>}{hasRemote && !hasLocal && onSaveLocal && <button className="small-action" title="將附件保存到本機文件匣" aria-label={`保存 ${row.filename} 到本機`} disabled={busy} onClick={() => onSaveLocal(row)}>保存</button>}{onChangeImport && <button className={`small-action ${row.revoked_at ? "" : "revoke-action"}`} aria-label={`${row.revoked_at ? "恢復" : "撤銷匯入"} ${row.filename}`} disabled={busy} onClick={() => onChangeImport(row)}>{row.revoked_at ? "恢復" : "撤銷匯入"}</button>}</span><span className="file-state" title={hasLocal ? "本機已有副本" : hasRemote ? "目前只保留遠端來源" : "本機已有副本"}>{stateLabel}</span></li>;
  })}</ul>;
}

function JobList({ rows, expanded = false, onOpenDocument }: { rows: Job[]; expanded?: boolean; onOpenDocument?: (documentId: string) => void }) {
  if (!rows.length) return <EmptyState title="還沒有匯入紀錄" detail="上傳文件或匯入 CSV 後，這裡會列出處理狀態。" />;
  const statusLabels: Record<string, string> = { completed: "完成", duplicate: "內容重複", partial: "部分完成", revoked: "已撤銷", restored: "已恢復", skipped_revoked: "略過已撤銷", failed: "失敗" };
  return <div className={expanded ? "job-list expanded" : "job-list"}>{rows.map((job) => <div className="job-row" key={job.id}><span className="job-type">{job.source_type === "gmail_sync" || job.source_type === "codex_mcp" ? "GMAIL" : job.source_type === "csv" ? "CSV" : "DOC"}</span><span className="job-info"><strong>{job.source_type === "document_lifecycle" ? "文件匯入狀態" : job.source_type === "gmail_sync" ? "舊版 Gmail 同步" : job.source_type === "codex_mcp" ? "Codex MCP 收錄" : job.target_module === "finance" ? "財務資料匯入" : "文件匯入"}</strong><small title={job.summary}>{job.summary} · {new Date(job.created_at).toLocaleString("zh-TW")}</small></span>{job.document_id && onOpenDocument && <button className="text-button job-document-link" aria-label="查看這筆工作對應的文件" onClick={() => onOpenDocument(job.document_id as string)}>查看文件</button>}<span className={`job-status ${job.status}`}>{statusLabels[job.status] ?? job.status}</span></div>)}</div>;
}

function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

function AddDataDialog({ busy, onClose, onUpload, onSettings }: {
  busy: boolean;
  onClose: () => void;
  onUpload: (file: File | undefined, finance: boolean) => Promise<string>;
  onSettings: () => void;
}) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  async function importFile(file: File | undefined, finance: boolean) {
    if (!file) return;
    setWorking(true); setError(""); setStatus("");
    try { setStatus(await onUpload(file, finance)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "匯入失敗"); }
    finally { setWorking(false); }
  }

  return <div className="data-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !working) onClose(); }}>
    <section className="data-dialog" role="dialog" aria-modal="true" aria-labelledby="add-data-title">
      <header className="data-dialog-header"><div><p className="eyebrow">資料入口</p><h2 id="add-data-title">新增資料</h2><p>先收錄來源，再依資料類型決定是否建立交易。</p></div><button className="icon-button" aria-label="關閉新增資料" title="關閉新增資料" disabled={working} onClick={onClose}>×</button></header>
      <div className="data-options">
        <article className="data-option"><span className="data-option-icon">DOC</span><div><h3>只收錄文件</h3><p>PDF、JPG、PNG 或其他 CSV 來源會進入文件匣；PDF 會在文件詳情中分析、核對後匯入。</p><label className="button secondary">加入文件<input type="file" accept=".pdf,.jpg,.jpeg,.png,.csv" disabled={busy || working} onChange={(event) => { void importFile(event.target.files?.[0], false); event.currentTarget.value = ""; }} /></label></div></article>
        <article className="data-option"><span className="data-option-icon csv">CSV</span><div><h3>收錄並建立交易</h3><p>通用 CSV 會先做 SHA-256 去重，再解析有效資料列；結果會顯示新增或略過筆數。</p><label className="button primary">匯入財務 CSV<input type="file" accept=".csv,text/csv" disabled={busy || working} onChange={(event) => { void importFile(event.target.files?.[0], true); event.currentTarget.value = ""; }} /></label></div></article>
        <article className="data-option"><span className="data-option-icon gmail">MCP</span><div><h3>Gmail 自動收錄</h3><p>Codex 排程會透過已連線的 Gmail 工具抓取帳單；網站不保存 Google OAuth 設定或 token。</p><p className="settings-note">自動收錄後仍會經過解鎖、版型辨識與核對。</p><button className="text-button" onClick={onSettings}>查看自動化狀態 <span>→</span></button></div></article>
      </div>
      {working && <p className="transaction-loading" role="status">正在處理資料…</p>}
      {error && <div className="notice error" role="alert">{error}</div>}
      {status && <div className="notice success" role="status">{status}</div>}
      <p className="data-dialog-note">文件收錄成功不等於財務入帳成功；每份文件的交易與處理歷史可在「文件詳情」查看。</p>
    </section>
  </div>;
}

function DocumentDetailDialog({ documentId, onClose, onPreview, onSaveLocal, onChangeImport, onImported }: {
  documentId: string;
  onClose: () => void;
  onPreview: (document: DocumentRow) => void;
  onSaveLocal: (document: DocumentRow) => void;
  onChangeImport: (document: DocumentRow) => void;
  onImported: () => Promise<void>;
}) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [statement, setStatement] = useState<Statement | null>(null);
  const [loading, setLoading] = useState(true);
  const [statementBusy, setStatementBusy] = useState(false);
  const [error, setError] = useState("");
  const [passwordHint, setPasswordHint] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setDetail(null); setStatement(null); setPasswordHint("");
    Promise.all([api.documentDetail(documentId), api.statements()]).then(async ([result, statements]) => {
      const matched = statements.find((item) => item.document_id === documentId);
      const review = matched ? await api.statementDetail(matched.statement_id) : null;
      if (!active) return;
      setDetail(result);
      setStatement(review);
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "無法載入文件詳情"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [documentId, retry]);

  async function analyzeStatement() {
    if (!detail?.document) return;
    setStatementBusy(true); setError("");
    try {
      const result = await api.analyzeStatement(documentId, { filename: detail.document.filename, body: passwordHint, allow_ai_analysis: false });
      setStatement(result);
      setRetry((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "帳單分析失敗");
    } finally { setStatementBusy(false); }
  }

  async function confirmStatement() {
    if (!statement) return;
    setStatementBusy(true); setError("");
    try {
      await api.confirmStatement(statement.statement_id, statement.review_version);
      setStatement(await api.statementDetail(statement.statement_id));
      await onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "帳單匯入失敗");
    } finally { setStatementBusy(false); }
  }

  const document = detail?.document;
  const isPdf = document?.content_type.includes("pdf") || document?.filename.toLowerCase().endsWith(".pdf");
  const hasGmailSource = detail?.sources.some((source) => source.type === "gmail_attachment" || source.type === "codex_mcp_gmail") ?? false;
  return <div className="data-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="detail-dialog" role="dialog" aria-modal="true" aria-labelledby="document-detail-title">
      <header className="data-dialog-header"><div><p className="eyebrow">文件詳情</p><h2 id="document-detail-title">{document?.filename ?? "載入文件中"}</h2><p>來源、收錄狀態、關聯交易與處理紀錄集中在這裡。</p></div><button className="icon-button" aria-label="關閉文件詳情" title="關閉文件詳情" onClick={onClose}>×</button></header>
      {loading && <p className="transaction-loading" role="status">正在載入文件詳情…</p>}
      {error && <><div className="notice error" role="alert">{error}</div><button className="small-action" onClick={() => setRetry((value) => value + 1)}>重新載入</button></>}
      {detail && document && <div className="detail-content">
        <div className="detail-meta"><span className={document.revoked_at ? "connection-state" : "connection-state ready"}>{document.revoked_at ? "已撤銷" : "有效文件"}</span><span>{formatBytes(document.size_bytes)} · 收錄於 {new Date(document.created_at).toLocaleString("zh-TW")}</span></div>
        {document.revoked_at && <p className="lifecycle-note">撤銷原因：{document.revocation_reason || "未提供"}</p>}
        {isPdf && <section className="detail-section statement-import-section"><div className="panel-heading"><div><h3>匯入家庭收支</h3><p>先解鎖與解析，再核對交易，確認後才會寫入收支與 Excel。</p></div><div className="detail-actions">{(!statement || statement.status === "pending") && <button className="small-action" disabled={statementBusy || document.revoked_at !== null} onClick={() => void analyzeStatement()}>{statementBusy ? "處理中…" : statement ? "重新分析" : "分析帳單"}</button>}{statement?.status === "ready" && <button className="small-action primary-action" disabled={statementBusy || document.revoked_at !== null} onClick={() => void confirmStatement()}>{statementBusy ? "匯入中…" : "確認匯入"}</button>}</div></div>{!hasGmailSource && <label className="statement-hint-field"><span>郵件中的密碼規則提示（選填，不要貼實際密碼）</span><textarea rows={3} maxLength={20_000} value={passwordHint} onChange={(event) => setPasswordHint(event.target.value)} placeholder="例如：PDF 密碼為身分證字號，英文字母請用大寫。" /><small>Codex MCP 收錄會帶入遮罩後提示；只有純本機文件才需要補充。</small></label>}{!statement && <p className="statement-help">這份 PDF 尚未分析。系統會使用已遮罩的郵件密碼提示與本機解鎖資料，成功後才顯示可匯入的交易。</p>}{statement && <><div className="statement-summary"><span className={`connection-state ${statement.status === "ready" || statement.status === "imported" ? "ready" : ""}`}>{statement.status === "ready" ? "待確認" : statement.status === "imported" ? "已匯入" : "待處理"}</span><span>{statement.bank_id} · {statementPeriod(statement)} · {statement.line_count} 筆交易列</span></div>{statement.status === "pending" && <p className="statement-help">{statementReason(statement.reason_code)}</p>}{statement.status === "imported" && <p className="notice success" role="status">這份帳單已匯入家庭收支；重複按下不會建立第二份交易。</p>}{statement.status === "ready" && <StatementReviewTable statement={statement} />}</>}</section>}
        <section className="detail-section"><div className="panel-heading"><div><h3>來源</h3><p>來源可用性與本機副本狀態</p></div><div className="detail-actions">{isPdf && <button className="small-action" onClick={() => onPreview(document)}>預覽 PDF</button>}{detail.sources.some((source) => source.type === "gmail_attachment" && !source.has_local_copy) && <button className="small-action" onClick={() => onSaveLocal(document)}>保存本機副本</button>}<button className={`small-action ${document.revoked_at ? "" : "revoke-action"}`} onClick={() => onChangeImport(document)}>{document.revoked_at ? "恢復文件" : "撤銷匯入"}</button></div></div><ul className="detail-source-list">{detail.sources.map((source) => <li key={`${source.type}-${source.availability}`}><strong>{source.type === "local_file" ? "本機文件匣" : source.type === "gmail_attachment" ? "Gmail 附件（舊版）" : source.type === "codex_mcp_gmail" ? "Gmail · Codex MCP" : source.type}</strong><span>{source.has_local_copy ? "已有本機副本" : source.type === "codex_mcp_gmail" ? "密碼提示已遮罩保存" : "僅保留來源參照"} · {source.availability === "available" ? "可取得" : source.availability === "unavailable" ? "目前不可取得" : "狀態未知"}</span></li>)}</ul></section>
        <section className="detail-section"><div className="panel-heading"><div><h3>關聯交易 <span className="detail-count">{detail.transactions.length}</span></h3><p>有效與已撤銷來源的原始交易紀錄</p></div></div><TransactionTable rows={detail.transactions} /></section>
        <section className="detail-section"><div className="panel-heading"><div><h3>匯入歷史 <span className="detail-count">{detail.jobs.length}</span></h3><p>這份文件的收錄、財務解析與狀態變更</p></div></div><JobList rows={detail.jobs} expanded /></section>
      </div>}
      <footer className="data-dialog-footer"><button className="button secondary" onClick={onClose}>關閉</button></footer>
    </section>
  </div>;
}

function StatementReviewTable({ statement }: { statement: Statement }) {
  const rows = statement.lines ?? [];
  if (!rows.length) return <p className="statement-help">帳單已確認本期沒有新增交易；確認後會留下帳單匯入紀錄，但不會虛構交易。</p>;
  return <div className="statement-review-table"><div className="statement-review-head"><span>日期</span><span>項目</span><span>金額</span></div>{rows.map((line) => <div className="statement-review-row" key={line.line_index}><span>{line.effective_transaction_date ?? line.transaction_date ?? "日期待確認"}{line.transaction_date_basis === "statement_closing_date" && <small className="statement-date-basis">結帳日認列</small>}</span><span>{line.description}</span><strong className={line.amount.startsWith("-") ? "expense" : "income"}>{money(line.amount, line.currency)}</strong></div>)}</div>;
}

function SettingsView({ report }: { report: (message: string, error?: string) => void }) {
  const [personalUnlock, setPersonalUnlock] = useState<PersonalUnlockStatus | null>(null);
  const [codexMcp, setCodexMcp] = useState<CodexMcpStatus | null>(null);
  const [ai, setAi] = useState<AiProviderStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [aiTestMessage, setAiTestMessage] = useState("");
  const [secret, setSecret] = useState({ national_id: "", birthday: "" });
  const [aiConfig, setAiConfig] = useState<{ provider: AiProvider; api_key: string; model: string }>({ provider: "groq", api_key: "", model: "openai/gpt-oss-20b" });
  const [activeGroup, setActiveGroup] = useState<SettingsGroup>("unlock");

  const defaultModel = (provider: AiProvider) => provider === "groq" ? "openai/gpt-oss-20b" : "gpt-4.1-mini";

  const load = useCallback(async () => {
    try {
      const [unlockStatus, codexMcpStatus, aiStatus] = await Promise.all([
        api.personalUnlock(), api.codexMcpStatus(), api.aiProvider(),
      ]);
      setPersonalUnlock(unlockStatus); setCodexMcp(codexMcpStatus); setAi(aiStatus);
      setAiConfig((current) => ({
        ...current,
        provider: aiStatus.provider ?? current.provider,
        model: aiStatus.model ?? defaultModel(aiStatus.provider ?? current.provider),
      }));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "無法讀取設定");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function createSecret(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await api.savePersonalUnlock({
        ...(secret.national_id.trim() ? { national_id: secret.national_id.trim() } : {}),
        ...(secret.birthday ? { birthday: secret.birthday } : {}),
      });
      setPersonalUnlock(result);
      setSecret({ national_id: "", birthday: "" });
      report("解鎖資料已安全保存到 Windows Credential Manager");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法保存解鎖資料"); }
    finally { setBusy(false); }
  }

  async function saveAi(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setAiTestMessage("");
    try {
      const result = await api.configureAiProvider(aiConfig);
      setAiConfig((current) => ({ ...current, api_key: "" }));
      setAi(result);
      setAiTestMessage("");
      report("AI 連線已驗證並切換；開啟加密 PDF 時會分析遮罩後的密碼提示");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法保存 AI 設定"); }
    finally { setBusy(false); }
  }

  async function testAi() {
    setBusy(true); setError(""); setAiTestMessage("");
    try {
      const result = await api.testAiProvider(aiConfig);
      setAiTestMessage(`連線成功：${result.provider === "groq" ? "Groq" : "OpenAI"} · ${result.model}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "AI 連線測試失敗"); }
    finally { setBusy(false); }
  }

  return <>
    {error && <div className="notice error" role="alert"><span>!</span>{error}<button onClick={() => void load()}>重試</button></div>}
    <nav className="settings-nav" aria-label="設定分組" role="tablist">
      {settingsGroups.map((group) => <button key={group.id} id={`settings-tab-${group.id}`} type="button" role="tab" aria-selected={activeGroup === group.id} aria-controls={`settings-panel-${group.id}`} onClick={() => setActiveGroup(group.id)}>
        <strong>{group.label}</strong><span>{group.description}</span>
      </button>)}
    </nav>
    <div className="settings-layout">
      {activeGroup === "categories" && <section className="settings-section" id="settings-panel-categories" role="tabpanel" aria-labelledby="settings-tab-categories"><CategorySettings /></section>}
      {activeGroup === "unlock" && <section className="settings-section" id="settings-panel-unlock" role="tabpanel" aria-labelledby="settings-tab-unlock" tabIndex={-1}>
        <div className="settings-heading"><div><p className="eyebrow">本機保管</p><h2>文件解鎖</h2><p>只需保存身分證字號、出生日期，或其中一項。系統依郵件提示在本機組合密碼。</p></div><span className={personalUnlock?.has_national_id || personalUnlock?.has_birthday ? "connection-state ready" : "connection-state"}>{personalUnlock?.has_national_id || personalUnlock?.has_birthday ? "已保存" : "未設定"}</span></div>
        <form className="settings-form" onSubmit={(event) => void createSecret(event)}>
          <label>身分證字號<input type="password" autoComplete="off" maxLength={64} value={secret.national_id} onChange={(event) => setSecret({ ...secret, national_id: event.target.value })} placeholder={personalUnlock?.has_national_id ? "已保存；留白不變" : "輸入身分證字號"} /></label>
          <label>出生日期<input type="date" value={secret.birthday} onChange={(event) => setSecret({ ...secret, birthday: event.target.value })} /></label>
          <button className="button primary" disabled={busy || (!secret.national_id.trim() && !secret.birthday)}>安全保存</button>
        </form>
        <p className="settings-note">身分證：{personalUnlock?.has_national_id ? "已保存" : "未保存"} · 生日：{personalUnlock?.has_birthday ? "已保存" : "未保存"}。留白的欄位不會覆蓋已保存資料；原始值不會從伺服器回傳。</p>
      </section>}

      {activeGroup === "advanced" && <section className="settings-section" id="settings-panel-advanced" role="tabpanel" aria-labelledby="settings-tab-advanced" tabIndex={-1}>
        <div className="settings-heading"><div><p className="eyebrow">可選服務</p><h2>AI 密碼規則辨識</h2><p>保存 API key 後，開啟加密 PDF 時會自動分析遮罩後的郵件提示；可能產生 API 用量。身分資料與組合密碼不會送出。</p></div><span className={ai?.configured && ai.credential_available ? "connection-state ready" : "connection-state"}>{ai?.configured ? ai.credential_available ? "作用中" : "憑證遺失" : "未設定"}</span></div>
        <div className="provider-active" aria-live="polite">
          <span>作用中 Provider<strong>{ai?.provider ? ai.provider === "groq" ? "Groq" : "OpenAI" : "尚未啟用"}</strong></span>
          <span>作用中模型<strong>{ai?.model ?? "尚未設定"}</strong></span>
          <span>安全憑證<strong>{ai?.credential_available ? "Windows Credential Manager 可用" : ai?.configured ? "找不到已保存的 API key" : "尚未保存"}</strong></span>
        </div>
        <form className="settings-form settings-form-two" onSubmit={(event) => void saveAi(event)}>
          <label>Provider<select value={aiConfig.provider} onChange={(event) => { const provider = event.target.value as AiProvider; setAiConfig({ ...aiConfig, provider, model: defaultModel(provider) }); setAiTestMessage(""); }}><option value="groq">Groq（免費優先）</option><option value="openai">OpenAI（既有相容）</option></select></label>
          <label>AI API key<input required type="password" autoComplete="new-password" value={aiConfig.api_key} onChange={(event) => { setAiConfig({ ...aiConfig, api_key: event.target.value }); setAiTestMessage(""); }} placeholder={ai?.configured ? "輸入 key 以測試並切換" : aiConfig.provider === "groq" ? "gsk_..." : "sk-..."} /></label>
          <label>模型<input required maxLength={120} value={aiConfig.model} onChange={(event) => { setAiConfig({ ...aiConfig, model: event.target.value }); setAiTestMessage(""); }} /></label>
          <div className="provider-actions"><button type="button" className="button secondary" disabled={busy || !aiConfig.api_key.trim() || !aiConfig.model.trim()} onClick={() => void testAi()}>{busy ? "處理中…" : "測試連線"}</button><button type="submit" className="button primary" disabled={busy || !aiConfig.api_key.trim() || !aiConfig.model.trim()}>{busy ? "處理中…" : "保存並切換"}</button></div>
        </form>
        {aiTestMessage && <p className="settings-note provider-test-success" role="status">{aiTestMessage}。尚未更改作用中設定；按「保存並切換」後才會生效。</p>}
        {ai?.configured && !ai.credential_available && <p className="settings-note provider-warning" role="alert">資料庫仍保留 Provider 設定，但 Windows Credential Manager 找不到對應 API key。請重新測試並保存，否則系統不會呼叫 AI。</p>}
        <p className="settings-note">Groq 目前提供 Free Plan；額度與支援模型可能由供應商調整。API key 只保存到 Windows Credential Manager，且只會把遮罩後的密碼提示送出。</p>
      </section>}

      {activeGroup === "connections" && <section className="settings-section" id="settings-panel-connections" role="tabpanel" aria-labelledby="settings-tab-connections" tabIndex={-1}>
        <div className="settings-heading"><div><p className="eyebrow">外部自動化</p><h2>Codex MCP 帳單收錄</h2><p>Codex 使用已授權的 Gmail 工具尋找帳單，將附件與遮罩後的密碼提示送進本機系統。</p></div><span className="connection-state ready">Codex 管理</span></div>
        <div className="automation-flow" aria-label="Codex MCP 自動化流程">
          <span><strong>1</strong>搜尋 Gmail 帳單信件</span>
          <span><strong>2</strong>下載附件與擷取密碼提示</span>
          <span><strong>3</strong>本機去重、解鎖與核對</span>
        </div>
        <p className="settings-note">網站不再要求 Google Cloud OAuth JSON，也不保存 Gmail token。Codex 排程與 Gmail 授權在 Codex 應用程式中管理。</p>
        <p className="settings-note" role="status">{codexMcp?.last_import_at ? `最近收到附件：${new Date(codexMcp.last_import_at).toLocaleString("zh-TW")} · ${codexMcp.last_import_status === "completed" ? "已收錄" : codexMcp.last_import_status === "duplicate" ? "內容重複，已略過" : codexMcp.last_import_status ?? "狀態未知"}` : "尚未收到 Codex MCP 自動化匯入的附件。"}</p>
        <ExcelExportSettings />
      </section>}
    </div>
  </>;
}

const unlockErrorCodes = new Set(["pdf_password_required", "pdf_wrong_password"]);

function previewFailure(reason: unknown) {
  if (reason instanceof ApiError) {
    if (reason.code === "pdf_password_required") return { code: reason.code, message: "尚無可用的解鎖資料或密碼提示。請在設定保存身分資料；本機文件可補上郵件中的密碼提示。" };
    if (reason.code === "pdf_wrong_password") return { code: reason.code, message: "郵件提示組成的密碼無法開啟這份 PDF。請核對提示與已保存的資料。" };
    if (reason.code === "document_source_unavailable") return { code: reason.code, message: "目前無法取得這份文件的本機副本；請重新收錄原始附件。" };
    return { code: reason.code ?? "preview_failed", message: reason.message };
  }
  return { code: "preview_failed", message: reason instanceof Error ? reason.message : "無法預覽 PDF" };
}

function PdfPreviewDialog({ document, onClose }: { document: DocumentRow; onClose: () => void }) {
  const dialog = useRef<HTMLElement>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [allowAi, setAllowAi] = useState(false);
  const [aiConfigured, setAiConfigured] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const [extractionStatus, setExtractionStatus] = useState("");
  const [unlockOpen, setUnlockOpen] = useState(false);
  const previewRequest = useRef(0);
  const initialPreviewDocument = useRef("");
  const needsUnlock = unlockErrorCodes.has(errorCode);

  useDialogFocus(dialog, onClose);
  useEffect(() => {
    if (initialPreviewDocument.current === document.id) return;
    initialPreviewDocument.current = document.id;
    let active = true;
    void api.aiProvider().then((status) => {
      if (!active) return;
      const aiAvailable = status.configured && status.credential_available;
      setAiConfigured(aiAvailable);
      setAllowAi(aiAvailable);
      void requestPreview(aiAvailable);
    }).catch(() => { if (active) void requestPreview(false); });
    return () => { active = false; };
  }, [document.id]);
  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  async function requestPreview(useAi = allowAi) {
    const requestId = ++previewRequest.current;
    setBusy(true); setError(""); setErrorCode("");
    try {
      const result = await api.preview(document.id, {
        subject,
        body,
        allow_ai_analysis: useAi,
      });
      if (requestId !== previewRequest.current) return;
      const nextUrl = URL.createObjectURL(result.blob);
      setPdfUrl((current) => { if (current) URL.revokeObjectURL(current); return nextUrl; });
      setExtractionStatus(result.extraction ?? "");
      setUnlockOpen(false);
    } catch (reason) {
      if (requestId !== previewRequest.current) return;
      const failure = previewFailure(reason);
      setErrorCode(failure.code);
      setError(failure.message);
      setUnlockOpen(unlockErrorCodes.has(failure.code));
    } finally { if (requestId === previewRequest.current) setBusy(false); }
  }

  function preview(event: React.FormEvent) {
    event.preventDefault();
    void requestPreview();
  }

  return <div className="preview-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialog} className="preview-dialog" role="dialog" aria-modal="true" aria-labelledby="preview-title" tabIndex={-1}>
      <header className="preview-header"><div><p className="eyebrow">文件預覽</p><h2 id="preview-title">{document.filename}</h2></div><button className="icon-button" data-dialog-initial-focus aria-label="關閉預覽" title="關閉預覽" onClick={onClose}>×</button></header>
      <div className="preview-body">
        <form className="preview-controls" onSubmit={preview}>
          <div className="preview-status"><p className="eyebrow">預覽狀態</p><strong>{busy ? "正在準備 PDF" : pdfUrl ? "PDF 已載入" : needsUnlock ? "需要解鎖資料" : "尚未取得預覽"}</strong><p>這裡只檢視文件，不會建立財務交易。</p></div>
          {error && <div className="notice error" role="alert">{error}</div>}
          {!unlockOpen && <button type="button" className="small-action preview-unlock-toggle" disabled={busy} onClick={() => setUnlockOpen(true)}>{needsUnlock ? "查看解鎖提示" : "顯示解鎖選項"}</button>}
          {unlockOpen && <div className="preview-unlock-form">
            <div className="preview-section-heading"><strong>解鎖提示</strong><button type="button" className="text-button" onClick={() => setUnlockOpen(false)}>收起</button></div>
            <label>郵件主旨（選填）<input maxLength={500} value={subject} onChange={(event) => setSubject(event.target.value)} /></label>
            <label>密碼提示（純本機文件才需要）<textarea rows={8} maxLength={20_000} value={body} onChange={(event) => setBody(event.target.value)} placeholder="例如：密碼為身分證末四碼加出生日期 YYYYMMDD" /></label>
            <label className="check-row"><input type="checkbox" checked={allowAi} disabled={!aiConfigured} onChange={(event) => setAllowAi(event.target.checked)} /><span>使用 AI 辨識遮罩後的提示{!aiConfigured ? "（請先在設定保存 API key）" : ""}</span></label>
            <button className="button primary" disabled={busy}>{busy ? "正在處理…" : "重新產生預覽"}</button>
            <p className="settings-note">Codex MCP 收錄的 Gmail 文件會使用已遮罩的郵件提示；解密只在本機處理，原始 PDF 不變。AI 不會收到身分資料或實際密碼。</p>
          </div>}
          {error && !needsUnlock && <button type="button" className="small-action" disabled={busy} onClick={() => void requestPreview()}>重試預覽</button>}
          {pdfUrl && <p className="settings-note">預覽成功不代表已建立財務交易；PDF 仍只是共用文件。</p>}
          {extractionStatus === "unavailable" && <div className="notice info" role="status">OCR 尚未就緒，但仍可檢視 PDF 頁面；請確認 Tesseract 與 PDFium 依賴。</div>}
          {extractionStatus === "language_unavailable" && <div className="notice info" role="status">OCR 語言資料尚未就緒，但仍可檢視 PDF 頁面；請檢查 FAMILY_FINANCE_HUB_OCR_LANG。</div>}
          {extractionStatus === "failed" && <div className="notice info" role="status">OCR 處理未完成，但仍可檢視完整 PDF。</div>}
          {extractionStatus === "partial" && <div className="notice info" role="status">OCR 只完成部分頁面，但仍可檢視完整 PDF。</div>}
          {extractionStatus === "insufficient" && <div className="notice info" role="status">OCR 未取得足夠文字，但仍可檢視 PDF 頁面。</div>}
        </form>
        <div className="pdf-stage">{pdfUrl ? <iframe title={`PDF 預覽：${document.filename}`} src={pdfUrl} /> : <EmptyState title={busy ? "正在準備預覽" : needsUnlock ? "需要解鎖資料" : "尚未取得預覽"} detail={needsUnlock ? "請到設定保存身分資料，或在左側補充郵件提示；預覽不會建立交易。" : "文件預覽會顯示在這裡。"} />}</div>
      </div>
    </section>
  </div>;
}
