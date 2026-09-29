import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type AiProvider, type AiProviderStatus, type Dashboard, type DocumentDetail, type DocumentRow, type Job, type Transaction, type PersonalUnlockStatus, type GmailStatus, type TransactionPage, type ImportImpact, type SearchResult } from "./api";
import { ImportLifecycleDialog } from "./ImportLifecycleDialog";
import { useDialogFocus } from "./useDialogFocus";
import { EmptyState } from "./EmptyState";
import { TransactionTable } from "./TransactionTable";
import { ExcelExportSettings } from "./ExcelExportSettings";

type View = "overview" | "documents" | "transactions" | "activity" | "settings" | "search";
type SettingsGroup = "connections" | "unlock" | "advanced";
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
  settings: "安全資料、文件解鎖與 Gmail 連線。",
  search: "從已收錄的文件與有效交易中查找資料。",
};
const settingsGroups: { id: SettingsGroup; label: string; description: string }[] = [
  { id: "unlock", label: "文件解鎖", description: "身分資料與 PDF 密碼" },
  { id: "connections", label: "連線服務", description: "Gmail 與 Excel 自動更新" },
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
      {view === "settings" && <SettingsView report={report} onRefresh={refresh} />}
      <footer className="page-footer"><span>家庭收支記錄 v0.1</span><span>資料保存在此 Windows 主機</span></footer>
    </main>
    {addDataOpen && <AddDataDialog busy={busy} onClose={() => setAddDataOpen(false)} onUpload={upload} onGmailSync={async () => { const result = await api.syncGmail(); await refresh(); return `Gmail 同步完成：新增附件 ${result.new_attachments} 份、交易 ${result.created_transactions} 筆、略過已撤銷 ${result.skipped_revoked} 份、失敗 ${result.failures} 件${result.truncated ? "；已達單次安全上限，請再次同步接續處理" : ""}`; }} onSettings={() => { setAddDataOpen(false); navigate("settings"); }} />}
    {detailDocumentId && <DocumentDetailDialog documentId={detailDocumentId} onClose={() => setDetailDocumentId(null)} onPreview={(document) => { setDetailDocumentId(null); setPreviewDocument(document); }} onSaveLocal={saveLocally} onChangeImport={openLifecycle} />}
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
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<TransactionPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const pageSize = 50;

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.transactions({ limit: pageSize, offset: page * pageSize, month: month || undefined, currency: currency || undefined })
      .then((response) => { if (active) { setResult(response); setError(""); } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "無法載入交易"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currency, month, page, refreshVersion]);

  useEffect(() => { setPage(0); }, [currency, month]);

  const pageCount = Math.max(1, Math.ceil((result?.total ?? 0) / pageSize));
  return <section className="panel page-panel transactions-page">
    <div className="panel-heading"><div><h2>收支明細</h2><p>{monthLabel(month)} · {currency || "全部幣別"} · 共 {result?.total ?? "—"} 筆交易</p></div>
      <div className="transaction-filters"><label className="month-filter">月份<input aria-label="依月份篩選交易" type="month" value={month} onChange={(event) => onPeriodChange(event.target.value, currency)} /></label><label className="month-filter">幣別<select aria-label="依幣別篩選交易" value={currency || "all"} onChange={(event) => onPeriodChange(month, event.target.value === "all" ? "" : event.target.value)}><option value="all">全部幣別</option>{currencies.map((option) => <option value={option} key={option}>{option}</option>)}</select></label></div>
    </div>
    {error && <div className="notice error" role="alert">{error}</div>}
    {loading && <p className="transaction-loading" role="status">正在載入交易…</p>}
    {!loading && !error && <TransactionTable rows={result?.items ?? []} onOpenDocument={onOpenDocument} emptyTitle={`${monthLabel(month)}尚無交易`} emptyDetail="目前沒有符合月份與幣別的有效交易。" />}
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
    const stateLabel = hasLocal ? "本機副本" : hasRemote ? "僅遠端來源" : "本機";
    return <li key={row.id}><span className={`file-icon ${isPdf ? "pdf" : row.content_type.includes("image") ? "image" : "csv"}`}>{isPdf ? "PDF" : row.content_type.includes("image") ? "IMG" : "CSV"}</span><span className="file-info"><a href={api.documentUrl(row.id)} target="_blank" rel="noreferrer"><strong>{row.filename}</strong></a><small>{formatBytes(row.size_bytes)} · {new Date(row.created_at).toLocaleDateString("zh-TW")}{hasRemote ? " · Gmail" : ""}</small>{row.revoked_at && <small className="revocation-detail">已撤銷 · {new Date(row.revoked_at).toLocaleDateString("zh-TW")}{row.revocation_reason ? ` · ${row.revocation_reason}` : ""}</small>}</span><span className="document-actions">{onDetail && <button className="small-action" aria-label={`查看 ${row.filename} 詳情`} onClick={() => onDetail(row.id)}>詳情</button>}{isPdf && onPreview && <button className="small-action" title="開啟 PDF 預覽" aria-label={`預覽 ${row.filename}`} onClick={() => onPreview(row)}>預覽</button>}{hasRemote && !hasLocal && onSaveLocal && <button className="small-action" title="將附件保存到本機文件匣" aria-label={`保存 ${row.filename} 到本機`} disabled={busy} onClick={() => onSaveLocal(row)}>保存</button>}{onChangeImport && <button className={`small-action ${row.revoked_at ? "" : "revoke-action"}`} aria-label={`${row.revoked_at ? "恢復" : "撤銷匯入"} ${row.filename}`} disabled={busy} onClick={() => onChangeImport(row)}>{row.revoked_at ? "恢復" : "撤銷匯入"}</button>}</span><span className="file-state" title={hasLocal ? "本機已有副本" : hasRemote ? "目前只保留遠端來源" : "本機已有副本"}>{stateLabel}</span></li>;
  })}</ul>;
}

function JobList({ rows, expanded = false, onOpenDocument }: { rows: Job[]; expanded?: boolean; onOpenDocument?: (documentId: string) => void }) {
  if (!rows.length) return <EmptyState title="還沒有匯入紀錄" detail="上傳文件或匯入 CSV 後，這裡會列出處理狀態。" />;
  const statusLabels: Record<string, string> = { completed: "完成", duplicate: "內容重複", partial: "部分完成", revoked: "已撤銷", restored: "已恢復", skipped_revoked: "略過已撤銷", failed: "失敗" };
  return <div className={expanded ? "job-list expanded" : "job-list"}>{rows.map((job) => <div className="job-row" key={job.id}><span className="job-type">{job.source_type === "gmail_sync" ? "GMAIL" : job.source_type === "csv" ? "CSV" : "DOC"}</span><span className="job-info"><strong>{job.source_type === "document_lifecycle" ? "文件匯入狀態" : job.source_type === "gmail_sync" ? "Gmail 同步" : job.target_module === "finance" ? "財務資料匯入" : "文件匯入"}</strong><small title={job.summary}>{job.summary} · {new Date(job.created_at).toLocaleString("zh-TW")}</small></span>{job.document_id && onOpenDocument && <button className="text-button job-document-link" aria-label="查看這筆工作對應的文件" onClick={() => onOpenDocument(job.document_id as string)}>查看文件</button>}<span className={`job-status ${job.status}`}>{statusLabels[job.status] ?? job.status}</span></div>)}</div>;
}

function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

function AddDataDialog({ busy, onClose, onUpload, onGmailSync, onSettings }: {
  busy: boolean;
  onClose: () => void;
  onUpload: (file: File | undefined, finance: boolean) => Promise<string>;
  onGmailSync: () => Promise<string>;
  onSettings: () => void;
}) {
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let active = true;
    api.gmailStatus().then((result) => { if (active) setGmail(result); }).catch(() => { if (active) setGmail(null); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function importFile(file: File | undefined, finance: boolean) {
    if (!file) return;
    setWorking(true); setError(""); setStatus("");
    try { setStatus(await onUpload(file, finance)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "匯入失敗"); }
    finally { setWorking(false); }
  }

  async function syncGmail() {
    setWorking(true); setError(""); setStatus("");
    try { setStatus(await onGmailSync()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Gmail 同步失敗"); }
    finally { setWorking(false); }
  }

  return <div className="data-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !working) onClose(); }}>
    <section className="data-dialog" role="dialog" aria-modal="true" aria-labelledby="add-data-title">
      <header className="data-dialog-header"><div><p className="eyebrow">資料入口</p><h2 id="add-data-title">新增資料</h2><p>先收錄來源，再依資料類型決定是否建立交易。</p></div><button className="icon-button" aria-label="關閉新增資料" title="關閉新增資料" disabled={working} onClick={onClose}>×</button></header>
      <div className="data-options">
        <article className="data-option"><span className="data-option-icon">DOC</span><div><h3>只收錄文件</h3><p>PDF、JPG、PNG 或其他 CSV 來源會進入文件匣；PDF 不會自動建立財務交易。</p><label className="button secondary">加入文件<input type="file" accept=".pdf,.jpg,.jpeg,.png,.csv" disabled={busy || working} onChange={(event) => { void importFile(event.target.files?.[0], false); event.currentTarget.value = ""; }} /></label></div></article>
        <article className="data-option"><span className="data-option-icon csv">CSV</span><div><h3>收錄並建立交易</h3><p>通用 CSV 會先做 SHA-256 去重，再解析有效資料列；結果會顯示新增或略過筆數。</p><label className="button primary">匯入財務 CSV<input type="file" accept=".csv,text/csv" disabled={busy || working} onChange={(event) => { void importFile(event.target.files?.[0], true); event.currentTarget.value = ""; }} /></label></div></article>
        <article className="data-option"><span className="data-option-icon gmail">G</span><div><h3>同步 Gmail 帳單</h3><p>只使用 Gmail 唯讀授權；附件先收錄，CSV 才會進入通用財務匯入。</p>{loading ? <p className="settings-note">正在檢查 Gmail 連線…</p> : gmail?.authorized ? <button className="button secondary" disabled={busy || working} onClick={() => void syncGmail()}>立即同步 Gmail</button> : <><p className="settings-note">尚未完成 Gmail 唯讀授權。</p><button className="text-button" onClick={onSettings}>前往設定連線 <span>→</span></button></>}</div></article>
      </div>
      {working && <p className="transaction-loading" role="status">正在處理資料…</p>}
      {error && <div className="notice error" role="alert">{error}</div>}
      {status && <div className="notice success" role="status">{status}</div>}
      <p className="data-dialog-note">文件收錄成功不等於財務入帳成功；每份文件的交易與處理歷史可在「文件詳情」查看。</p>
    </section>
  </div>;
}

function DocumentDetailDialog({ documentId, onClose, onPreview, onSaveLocal, onChangeImport }: {
  documentId: string;
  onClose: () => void;
  onPreview: (document: DocumentRow) => void;
  onSaveLocal: (document: DocumentRow) => void;
  onChangeImport: (document: DocumentRow) => void;
}) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setDetail(null);
    api.documentDetail(documentId).then((result) => { if (active) setDetail(result); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "無法載入文件詳情"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [documentId, retry]);

  const document = detail?.document;
  const isPdf = document?.content_type.includes("pdf") || document?.filename.toLowerCase().endsWith(".pdf");
  return <div className="data-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="detail-dialog" role="dialog" aria-modal="true" aria-labelledby="document-detail-title">
      <header className="data-dialog-header"><div><p className="eyebrow">文件詳情</p><h2 id="document-detail-title">{document?.filename ?? "載入文件中"}</h2><p>來源、收錄狀態、關聯交易與處理紀錄集中在這裡。</p></div><button className="icon-button" aria-label="關閉文件詳情" title="關閉文件詳情" onClick={onClose}>×</button></header>
      {loading && <p className="transaction-loading" role="status">正在載入文件詳情…</p>}
      {error && <><div className="notice error" role="alert">{error}</div><button className="small-action" onClick={() => setRetry((value) => value + 1)}>重新載入</button></>}
      {detail && document && <div className="detail-content">
        <div className="detail-meta"><span className={document.revoked_at ? "connection-state" : "connection-state ready"}>{document.revoked_at ? "已撤銷" : "有效文件"}</span><span>{formatBytes(document.size_bytes)} · 收錄於 {new Date(document.created_at).toLocaleString("zh-TW")}</span></div>
        {document.revoked_at && <p className="lifecycle-note">撤銷原因：{document.revocation_reason || "未提供"}</p>}
        <section className="detail-section"><div className="panel-heading"><div><h3>來源</h3><p>來源可用性與本機副本狀態</p></div><div className="detail-actions">{isPdf && <button className="small-action" onClick={() => onPreview(document)}>預覽 PDF</button>}{detail.sources.some((source) => source.type === "gmail_attachment" && !source.has_local_copy) && <button className="small-action" onClick={() => onSaveLocal(document)}>保存本機副本</button>}<button className={`small-action ${document.revoked_at ? "" : "revoke-action"}`} onClick={() => onChangeImport(document)}>{document.revoked_at ? "恢復文件" : "撤銷匯入"}</button></div></div><ul className="detail-source-list">{detail.sources.map((source) => <li key={`${source.type}-${source.availability}`}><strong>{source.type === "local_file" ? "本機文件匣" : source.type === "gmail_attachment" ? "Gmail 附件" : source.type}</strong><span>{source.has_local_copy ? "已有本機副本" : "僅保留來源參照"} · {source.availability === "available" ? "可取得" : source.availability === "unavailable" ? "目前不可取得" : "狀態未知"}</span></li>)}</ul></section>
        <section className="detail-section"><div className="panel-heading"><div><h3>關聯交易 <span className="detail-count">{detail.transactions.length}</span></h3><p>有效與已撤銷來源的原始交易紀錄</p></div></div><TransactionTable rows={detail.transactions} /></section>
        <section className="detail-section"><div className="panel-heading"><div><h3>匯入歷史 <span className="detail-count">{detail.jobs.length}</span></h3><p>這份文件的收錄、財務解析與狀態變更</p></div></div><JobList rows={detail.jobs} expanded /></section>
      </div>}
      <footer className="data-dialog-footer"><button className="button secondary" onClick={onClose}>關閉</button></footer>
    </section>
  </div>;
}

function SettingsView({ report, onRefresh }: { report: (message: string, error?: string) => void; onRefresh: () => Promise<void> }) {
  const [personalUnlock, setPersonalUnlock] = useState<PersonalUnlockStatus | null>(null);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [ai, setAi] = useState<AiProviderStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [secret, setSecret] = useState({ national_id: "", birthday: "" });
  const [aiConfig, setAiConfig] = useState<{ provider: AiProvider; api_key: string; model: string }>({ provider: "groq", api_key: "", model: "openai/gpt-oss-20b" });
  const [activeGroup, setActiveGroup] = useState<SettingsGroup>("unlock");

  const defaultModel = (provider: AiProvider) => provider === "groq" ? "openai/gpt-oss-20b" : "gpt-4.1-mini";

  const load = useCallback(async () => {
    try {
      const [unlockStatus, gmailStatus, aiStatus] = await Promise.all([
        api.personalUnlock(), api.gmailStatus(), api.aiProvider(),
      ]);
      setPersonalUnlock(unlockStatus); setGmail(gmailStatus); setAi(aiStatus);
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
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await api.configureAiProvider(aiConfig);
      setAiConfig((current) => ({ ...current, api_key: "" }));
      setAi({ configured: result.configured, provider: result.provider, model: result.model });
      report("AI 設定已保存；開啟加密 PDF 時會分析遮罩後的密碼提示");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法保存 AI 設定"); }
    finally { setBusy(false); }
  }

  async function configureGmail(file?: File) {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("OAuth JSON 格式不正確");
      await api.configureGmail(parsed as Record<string, unknown>);
      await load(); report("Gmail OAuth 設定已安全保存");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法讀取 Gmail OAuth 設定"); }
    finally { setBusy(false); }
  }

  async function authorizeGmail() {
    setBusy(true); setError("");
    try {
      await api.authorizeGmail();
      await load(); report("Gmail 已連線，只授予唯讀郵件權限");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Gmail 授權未完成"); }
    finally { setBusy(false); }
  }

  async function syncGmail() {
    setBusy(true); setError("");
    try {
      const result = await api.syncGmail();
      const suffix = result.truncated ? "；已達單次安全上限，請再次同步接續處理" : "";
      report(`Gmail 同步完成：新增附件 ${result.new_attachments} 份、交易 ${result.created_transactions} 筆、略過已撤銷 ${result.skipped_revoked} 份、失敗 ${result.failures} 件${suffix}`);
      await Promise.all([load(), onRefresh()]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Gmail 同步失敗"); }
    finally { setBusy(false); }
  }

  async function setGmailSchedule(enabled: boolean) {
    setBusy(true); setError("");
    try {
      await api.setGmailSchedule(enabled);
      await load();
      report(enabled ? "Gmail 自動同步已啟用" : "Gmail 自動同步已關閉");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法更新 Gmail 自動同步設定"); }
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
        <div className="settings-heading"><div><p className="eyebrow">可選服務</p><h2>AI 密碼規則辨識</h2><p>保存 API key 後，開啟加密 PDF 時會自動分析遮罩後的郵件提示；可能產生 API 用量。身分資料與組合密碼不會送出。</p></div><span className={ai?.configured ? "connection-state ready" : "connection-state"}>{ai?.configured ? `已設定 · ${ai.model}` : "未設定"}</span></div>
        <form className="settings-form settings-form-two" onSubmit={(event) => void saveAi(event)}>
          <label>Provider<select value={aiConfig.provider} onChange={(event) => { const provider = event.target.value as AiProvider; setAiConfig({ ...aiConfig, provider, model: defaultModel(provider) }); }}><option value="groq">Groq（免費優先）</option><option value="openai">OpenAI（既有相容）</option></select></label>
          <label>AI API key<input required type="password" autoComplete="new-password" value={aiConfig.api_key} onChange={(event) => setAiConfig({ ...aiConfig, api_key: event.target.value })} placeholder={ai?.configured ? "已設定；輸入新 key 可更新" : aiConfig.provider === "groq" ? "gsk_..." : "sk-..."} /></label>
          <label>模型<input required maxLength={120} value={aiConfig.model} onChange={(event) => setAiConfig({ ...aiConfig, model: event.target.value })} /></label>
          <button className="button secondary" disabled={busy || !aiConfig.api_key}>保存 AI 設定</button>
        </form>
        <p className="settings-note">Groq 目前提供 Free Plan；額度與支援模型可能由供應商調整。API key 只保存到 Windows Credential Manager，且只會把遮罩後的密碼提示送出。</p>
      </section>}

      {activeGroup === "connections" && <section className="settings-section" id="settings-panel-connections" role="tabpanel" aria-labelledby="settings-tab-connections" tabIndex={-1}>
        <div className="settings-heading"><div><p className="eyebrow">只讀連線</p><h2>Gmail 帳單</h2><p>預設搜尋全部可存取郵件（含垃圾郵件與封存），不設日期範圍；附件預設只保存來源參照。</p></div><span className={gmail?.authorized ? "connection-state ready" : "connection-state"}>{gmail?.authorized ? "已連線 · 唯讀" : gmail?.configured ? "待授權" : "未設定"}</span></div>
        {gmail && <p className="settings-note">同步狀態：{gmail.last_sync_status === "never" ? "尚未同步" : gmail.last_sync_status === "completed" ? "完成" : gmail.last_sync_status === "failed" ? "失敗" : gmail.last_sync_status === "running" ? "同步中" : "部分完成"}{gmail.last_successful_sync ? ` · 最近成功 ${new Date(gmail.last_successful_sync).toLocaleString("zh-TW")}` : ""}{gmail.last_error_summary ? ` · ${gmail.last_error_summary}` : ""}{gmail.full_sync_in_progress ? " · 初次同步尚在分批處理" : ""}</p>}
        <div className="gmail-actions"><label className="button secondary">選擇 OAuth 桌面設定<input type="file" accept="application/json,.json" disabled={busy} onChange={(event) => { void configureGmail(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label><button className="button secondary" disabled={busy || !gmail?.configured} onClick={() => void authorizeGmail()}>連接 Google 帳戶</button><button className="button primary" disabled={busy || !gmail?.authorized} onClick={() => void syncGmail()}>{busy ? "處理中…" : "立即同步 Gmail"}</button></div>
        {gmail && <div className="gmail-schedule"><label><input type="checkbox" checked={gmail.auto_sync_enabled} disabled={busy || !gmail.authorized} onChange={(event) => void setGmailSchedule(event.target.checked)} /><span>啟用每 {gmail.sync_interval_minutes} 分鐘自動同步</span></label>{gmail.auto_sync_enabled && gmail.next_sync_at && <span className="settings-note">下次同步：{new Date(gmail.next_sync_at).toLocaleString("zh-TW")}</span>}</div>}
        <p className="settings-note">請先在 Google Cloud 建立 OAuth 用戶端 ID，應用程式類型選「桌面應用程式」，啟用 Gmail API，下載 JSON 後於此選取。連線只要求 gmail.readonly 權限。</p>
        <ExcelExportSettings />
      </section>}
    </div>
  </>;
}

const unlockErrorCodes = new Set(["pdf_password_required", "pdf_wrong_password"]);

function previewFailure(reason: unknown) {
  if (reason instanceof ApiError) {
    if (reason.code === "pdf_password_required") return { code: reason.code, message: "尚無可用的解鎖資料或密碼提示。請在設定保存身分資料；若不是 Gmail 文件，請貼上郵件中的密碼提示。" };
    if (reason.code === "pdf_wrong_password") return { code: reason.code, message: "郵件提示組成的密碼無法開啟這份 PDF。請核對提示與已保存的資料。" };
    if (reason.code === "document_source_unavailable") return { code: reason.code, message: "目前無法取得這份文件的來源；若是 Gmail 附件，請先保存本機副本或重新同步。" };
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
      setAiConfigured(status.configured);
      setAllowAi(status.configured);
      void requestPreview(status.configured);
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
            <label>密碼提示（非 Gmail 文件才需要）<textarea rows={8} maxLength={20_000} value={body} onChange={(event) => setBody(event.target.value)} placeholder="例如：密碼為身分證末四碼加出生日期 YYYYMMDD" /></label>
            <label className="check-row"><input type="checkbox" checked={allowAi} disabled={!aiConfigured} onChange={(event) => setAllowAi(event.target.checked)} /><span>使用 AI 辨識遮罩後的提示{!aiConfigured ? "（請先在設定保存 API key）" : ""}</span></label>
            <button className="button primary" disabled={busy}>{busy ? "正在處理…" : "重新產生預覽"}</button>
            <p className="settings-note">Gmail 文件會讀取原郵件提示；解密只在本機處理，原始 PDF 不變。AI 不會收到身分資料或實際密碼。</p>
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
