import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Dashboard, type DocumentRow, type Job, type Transaction } from "./api";

type View = "overview" | "documents" | "activity";
const money = (value: string, currency: string) => new Intl.NumberFormat("zh-TW", { style: "currency", currency }).format(Number(value));
const groupedMoney = (dashboard: Dashboard, field: "income" | "expenses" | "net") => dashboard.currency_totals.length
  ? dashboard.currency_totals.map((total) => dashboard.currency_totals.length > 1 ? `${total.currency} ${money(total[field], total.currency)}` : money(total[field], total.currency)).join(" · ")
  : money("0", "TWD");

export default function App() {
  const [view, setView] = useState<View>("overview");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<{ documents: DocumentRow[]; transactions: Transaction[] } | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [d, docs, tx, j] = await Promise.all([api.dashboard(), api.documents(), api.transactions(), api.jobs()]);
      setDashboard(d); setDocuments(docs); setTransactions(tx); setJobs(j); setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "無法連線至家庭收支記錄服務");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function upload(file: File | undefined, finance: boolean) {
    if (!file) return;
    setBusy(true); setMessage(""); setError("");
    try {
      const result = await api.upload(file, finance);
      setMessage(finance ? `CSV 匯入完成，新增 ${result.created_transactions ?? 0} 筆交易` : result.duplicate ? "相同內容已存在，沿用既有文件" : "文件已加入文件匣");
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "匯入失敗");
    } finally { setBusy(false); }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) { setSearchResult(null); return; }
    try { setSearchResult(await api.search(query.trim())); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "搜尋失敗"); }
  }

  const visibleDocuments = useMemo(() => searchResult?.documents ?? documents, [documents, searchResult]);
  const visibleTransactions = useMemo(() => searchResult?.transactions ?? transactions, [transactions, searchResult]);

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#overview" onClick={() => setView("overview")}><span className="brand-mark">家</span><span>家庭收支記錄</span></a>
      <p className="nav-label">工作區</p>
      <nav aria-label="主要導覽">
        <button className={view === "overview" ? "nav-item active" : "nav-item"} onClick={() => setView("overview")}><span className="nav-icon">▦</span>總覽</button>
        <button className={view === "documents" ? "nav-item active" : "nav-item"} onClick={() => setView("documents")}><span className="nav-icon">▤</span>文件</button>
        <button className={view === "activity" ? "nav-item active" : "nav-item"} onClick={() => setView("activity")}><span className="nav-icon">◷</span>匯入紀錄</button>
      </nav>
      <div className="sidebar-foot"><span className="status-dot" />本機資料庫<span className="local-label">LOCAL</span></div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb">家庭資料 <span>/</span> {view === "overview" ? "總覽" : view === "documents" ? "文件" : "匯入紀錄"}</div>
        <form className="search-form" onSubmit={search} role="search"><span aria-hidden="true">⌕</span><input aria-label="搜尋文件與交易" placeholder="搜尋文件與交易" value={query} onChange={(event) => setQuery(event.target.value)} /><button type="submit" title="搜尋" aria-label="搜尋">↵</button></form>
      </header>

      <section className="page-heading">
        <div><p className="eyebrow">家庭資料中心</p><h1>{view === "overview" ? "收支總覽" : view === "documents" ? "文件" : "匯入紀錄"}</h1><p className="subheading">{view === "overview" ? "掌握已匯入資料與家庭收支。" : view === "documents" ? "所有家庭文件的共用資料來源。" : "查看文件與財務資料的匯入結果。"}</p></div>
        <div className="actions"><label className="button secondary">加入文件<input type="file" accept=".pdf,.jpg,.jpeg,.png,.csv" disabled={busy} onChange={(event) => { void upload(event.target.files?.[0], false); event.currentTarget.value = ""; }} /></label><label className="button primary">匯入財務 CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { void upload(event.target.files?.[0], true); event.currentTarget.value = ""; }} /></label></div>
      </section>

      {error && <div className="notice error" role="alert"><span>!</span>{error}<button onClick={() => void refresh()}>重試</button></div>}
      {message && <div className="notice success" role="status"><span>✓</span>{message}<button aria-label="關閉訊息" onClick={() => setMessage("")}>×</button></div>}

      {(view === "overview" || searchResult) && <>
        <section className="metrics" aria-label="收支摘要">
          <article className="metric"><div className="metric-top"><span>交易筆數</span><span className="metric-icon green">↗</span></div><strong>{dashboard?.transaction_count ?? "—"}</strong><small>已匯入交易</small></article>
          <article className="metric"><div className="metric-top"><span>收入</span><span className="metric-icon blue">＋</span></div><strong>{dashboard ? groupedMoney(dashboard, "income") : "—"}</strong><small>依幣別分別計算</small></article>
          <article className="metric"><div className="metric-top"><span>支出</span><span className="metric-icon coral">－</span></div><strong>{dashboard ? groupedMoney(dashboard, "expenses") : "—"}</strong><small>依幣別分別計算</small></article>
          <article className="metric"><div className="metric-top"><span>淨額</span><span className="metric-icon lilac">＝</span></div><strong>{dashboard ? groupedMoney(dashboard, "net") : "—"}</strong><small>收入減去支出</small></article>
        </section>
        <section className="content-grid">
          <div className="panel transactions-panel">
            <div className="panel-heading"><div><h2>{searchResult ? "交易搜尋結果" : "最近交易"}</h2><p>由已匯入的 CSV 建立</p></div><button className="text-button" onClick={() => { setView("activity"); setSearchResult(null); }}>查看匯入紀錄 <span>→</span></button></div>
            <TransactionTable rows={visibleTransactions.slice(0, 8)} />
          </div>
          <div className="panel documents-panel">
            <div className="panel-heading"><div><h2>{searchResult ? "文件搜尋結果" : "最近文件"}</h2><p>共 {documents.length} 份文件</p></div><button className="icon-button" title="查看所有文件" aria-label="查看所有文件" onClick={() => { setView("documents"); setSearchResult(null); }}>→</button></div>
            <DocumentList rows={visibleDocuments.slice(0, 5)} />
          </div>
        </section>
        <section className="panel jobs-panel"><div className="panel-heading"><div><h2>最近匯入</h2><p>文件與財務匯入處理狀態</p></div><button className="text-button" onClick={() => setView("activity")}>全部紀錄 <span>→</span></button></div><JobList rows={jobs.slice(0, 4)} /></section>
      </>}

      {view === "documents" && !searchResult && <section className="panel page-panel"><div className="panel-heading"><div><h2>文件匣</h2><p>PDF、圖片及 CSV 都先保存在共用文件資料層</p></div></div><DocumentList rows={documents} expanded /></section>}
      {view === "activity" && <section className="panel page-panel"><div className="panel-heading"><div><h2>工作與匯入歷史</h2><p>最新 100 筆處理紀錄</p></div></div><JobList rows={jobs} expanded /></section>}
      <footer className="page-footer"><span>家庭收支記錄 v0.1</span><span>資料保存在此 Windows 主機</span></footer>
    </main>
  </div>;
}

function TransactionTable({ rows }: { rows: Transaction[] }) {
  if (!rows.length) return <EmptyState title="尚無交易資料" detail="匯入通用 CSV 後，交易會顯示在這裡。" />;
  return <div className="table-wrap"><table><thead><tr><th>日期</th><th>項目</th><th>金額</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td className="date-cell">{row.date ?? "未提供"}</td><td><span className="transaction-name">{row.description}</span></td><td className={Number(row.amount) < 0 ? "amount expense" : "amount income"}>{money(row.amount, row.currency)}</td></tr>)}</tbody></table></div>;
}

function DocumentList({ rows, expanded = false }: { rows: DocumentRow[]; expanded?: boolean }) {
  if (!rows.length) return <EmptyState title="文件匣目前是空的" detail="加入 PDF、JPG、PNG 或 CSV 文件開始整理。" />;
  return <ul className={expanded ? "document-list expanded" : "document-list"}>{rows.map((row) => <li key={row.id}><span className={`file-icon ${row.content_type.includes("pdf") ? "pdf" : row.content_type.includes("image") ? "image" : "csv"}`}>{row.content_type.includes("pdf") ? "PDF" : row.content_type.includes("image") ? "IMG" : "CSV"}</span><span className="file-info"><a href={api.documentUrl(row.id)} target="_blank" rel="noreferrer"><strong>{row.filename}</strong></a><small>{formatBytes(row.size_bytes)} · {new Date(row.created_at).toLocaleDateString("zh-TW")}</small></span><span className="file-state" title="已保存在文件匣">✓</span></li>)}</ul>;
}

function JobList({ rows, expanded = false }: { rows: Job[]; expanded?: boolean }) {
  if (!rows.length) return <EmptyState title="還沒有匯入紀錄" detail="上傳文件或匯入 CSV 後，這裡會列出處理狀態。" />;
  return <div className={expanded ? "job-list expanded" : "job-list"}>{rows.map((job) => <div className="job-row" key={job.id}><span className="job-type">{job.source_type === "csv" ? "CSV" : "DOC"}</span><span className="job-info"><strong>{job.target_module === "finance" ? "財務資料匯入" : "文件匯入"}</strong><small>{job.summary} · {new Date(job.created_at).toLocaleString("zh-TW")}</small></span><span className={`job-status ${job.status}`}>{job.status === "completed" ? "完成" : job.status === "duplicate" ? "內容重複" : job.status}</span></div>)}</div>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) { return <div className="empty-state"><span className="empty-mark">⌁</span><strong>{title}</strong><p>{detail}</p></div>; }
function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }
