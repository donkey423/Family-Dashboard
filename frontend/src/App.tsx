import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Dashboard, type DocumentRow, type Job, type Transaction, type SecretProfile, type DocumentSecurityProfile, type GmailStatus, type TransactionPage } from "./api";

type View = "overview" | "documents" | "transactions" | "activity" | "settings";
const money = (value: string, currency: string) => {
  try { return new Intl.NumberFormat("zh-TW", { style: "currency", currency }).format(Number(value)); }
  catch { return `${currency} ${value}`; }
};
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
  const [previewDocument, setPreviewDocument] = useState<DocumentRow | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [d, docs, tx, j] = await Promise.all([api.dashboard(), api.documents(), api.transactions({ limit: 8 }), api.jobs()]);
      setDashboard(d); setDocuments(docs); setTransactions(tx.items); setJobs(j); setError("");
      setRefreshVersion((version) => version + 1);
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

  const visibleDocuments = useMemo(() => searchResult?.documents ?? documents, [documents, searchResult]);
  const visibleTransactions = useMemo(() => searchResult?.transactions ?? transactions, [transactions, searchResult]);

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#overview" onClick={() => setView("overview")}><span className="brand-mark">家</span><span>家庭收支記錄</span></a>
      <p className="nav-label">工作區</p>
      <nav aria-label="主要導覽">
        <button className={view === "overview" ? "nav-item active" : "nav-item"} onClick={() => setView("overview")}><span className="nav-icon">▦</span>總覽</button>
        <button className={view === "documents" ? "nav-item active" : "nav-item"} onClick={() => setView("documents")}><span className="nav-icon">▤</span>文件</button>
        <button className={view === "transactions" ? "nav-item active" : "nav-item"} onClick={() => { setView("transactions"); setSearchResult(null); }}><span className="nav-icon">↕</span>交易</button>
        <button className={view === "activity" ? "nav-item active" : "nav-item"} onClick={() => setView("activity")}><span className="nav-icon">◷</span>匯入紀錄</button>
        <button className={view === "settings" ? "nav-item active" : "nav-item"} onClick={() => setView("settings")}><span className="nav-icon">⚙</span>設定</button>
      </nav>
      <div className="sidebar-foot"><span className="status-dot" />本機資料庫<span className="local-label">LOCAL</span></div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb">家庭資料 <span>/</span> {view === "overview" ? "總覽" : view === "documents" ? "文件" : view === "transactions" ? "交易" : view === "activity" ? "匯入紀錄" : "設定"}</div>
        <form className="search-form" onSubmit={search} role="search"><span aria-hidden="true">⌕</span><input aria-label="搜尋文件與交易" placeholder="搜尋文件與交易" value={query} onChange={(event) => setQuery(event.target.value)} /><button type="submit" title="搜尋" aria-label="搜尋">↵</button></form>
      </header>

      <section className="page-heading">
        <div><p className="eyebrow">家庭資料中心</p><h1>{view === "overview" ? "收支總覽" : view === "documents" ? "文件" : view === "transactions" ? "交易" : view === "activity" ? "匯入紀錄" : "設定"}</h1><p className="subheading">{view === "overview" ? "掌握已匯入資料與家庭收支。" : view === "documents" ? "所有家庭文件的共用資料來源。" : view === "transactions" ? "按月份檢視已匯入的收支明細。" : view === "activity" ? "查看文件與財務資料的匯入結果。" : "安全資料、文件規則與 Gmail 連線。"}</p></div>
        {view !== "settings" && <div className="actions"><label className="button secondary">加入文件<input type="file" accept=".pdf,.jpg,.jpeg,.png,.csv" disabled={busy} onChange={(event) => { void upload(event.target.files?.[0], false); event.currentTarget.value = ""; }} /></label><label className="button primary">匯入財務 CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { void upload(event.target.files?.[0], true); event.currentTarget.value = ""; }} /></label></div>}
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
            <div className="panel-heading"><div><h2>{searchResult ? "交易搜尋結果" : "最近交易"}</h2><p>由已匯入的 CSV 建立</p></div><button className="text-button" onClick={() => { setView("transactions"); setSearchResult(null); }}>查看全部交易 <span>→</span></button></div>
            <TransactionTable rows={visibleTransactions.slice(0, 8)} />
          </div>
          <div className="panel documents-panel">
            <div className="panel-heading"><div><h2>{searchResult ? "文件搜尋結果" : "最近文件"}</h2><p>共 {documents.length} 份文件</p></div><button className="icon-button" title="查看所有文件" aria-label="查看所有文件" onClick={() => { setView("documents"); setSearchResult(null); }}>→</button></div>
          <DocumentList rows={visibleDocuments.slice(0, 5)} onPreview={setPreviewDocument} onSaveLocal={saveLocally} busy={busy} />
          </div>
        </section>
        <section className="panel jobs-panel"><div className="panel-heading"><div><h2>最近匯入</h2><p>文件與財務匯入處理狀態</p></div><button className="text-button" onClick={() => setView("activity")}>全部紀錄 <span>→</span></button></div><JobList rows={jobs.slice(0, 4)} /></section>
      </>}

      {view === "documents" && !searchResult && <section className="panel page-panel"><div className="panel-heading"><div><h2>文件匣</h2><p>PDF、圖片及 CSV 都先進入共用文件資料層</p></div></div><DocumentList rows={documents} expanded onPreview={setPreviewDocument} onSaveLocal={saveLocally} busy={busy} /></section>}
      {view === "transactions" && !searchResult && <TransactionsView refreshVersion={refreshVersion} />}
      {view === "activity" && <section className="panel page-panel"><div className="panel-heading"><div><h2>工作與匯入歷史</h2><p>最新 100 筆處理紀錄</p></div></div><JobList rows={jobs} expanded /></section>}
      {view === "settings" && <SettingsView report={report} onRefresh={refresh} />}
      <footer className="page-footer"><span>家庭收支記錄 v0.1</span><span>資料保存在此 Windows 主機</span></footer>
    </main>
    {previewDocument && <PdfPreviewDialog document={previewDocument} onClose={() => setPreviewDocument(null)} />}
  </div>;
}

function TransactionsView({ refreshVersion }: { refreshVersion: number }) {
  const [month, setMonth] = useState("");
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<TransactionPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const pageSize = 50;

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.transactions({ limit: pageSize, offset: page * pageSize, month: month || undefined })
      .then((response) => { if (active) { setResult(response); setError(""); } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "無法載入交易"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [month, page, refreshVersion]);

  const pageCount = Math.max(1, Math.ceil((result?.total ?? 0) / pageSize));
  return <section className="panel page-panel transactions-page">
    <div className="panel-heading"><div><h2>收支明細</h2><p>共 {result?.total ?? "—"} 筆交易</p></div>
      <label className="month-filter">月份<input aria-label="依月份篩選交易" type="month" value={month} onChange={(event) => { setPage(0); setMonth(event.target.value); }} /></label>
      {month && <button className="text-button" onClick={() => { setPage(0); setMonth(""); }}>清除篩選</button>}
    </div>
    {error && <div className="notice error" role="alert">{error}</div>}
    {loading && <p className="transaction-loading" role="status">正在載入交易…</p>}
    {!loading && !error && <TransactionTable rows={result?.items ?? []} />}
    <div className="pagination" aria-label="交易分頁">
      <span>{result?.total ? `${page + 1} / ${pageCount} 頁` : "0 筆交易"}</span>
      <div><button className="small-action" disabled={page === 0 || loading} onClick={() => setPage((current) => Math.max(0, current - 1))}>上一頁</button><button className="small-action" disabled={(page + 1) * pageSize >= (result?.total ?? 0) || loading} onClick={() => setPage((current) => current + 1)}>下一頁</button></div>
    </div>
  </section>;
}

function TransactionTable({ rows }: { rows: Transaction[] }) {
  if (!rows.length) return <EmptyState title="尚無交易資料" detail="匯入通用 CSV 後，交易會顯示在這裡。" />;
  return <div className="table-wrap"><table><thead><tr><th>日期</th><th>項目</th><th>金額</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td className="date-cell">{row.date ?? "未提供"}</td><td><span className="transaction-name">{row.description}</span></td><td className={Number(row.amount) < 0 ? "amount expense" : "amount income"}>{money(row.amount, row.currency)}</td></tr>)}</tbody></table></div>;
}

function DocumentList({ rows, expanded = false, onPreview, onSaveLocal, busy = false }: { rows: DocumentRow[]; expanded?: boolean; onPreview?: (document: DocumentRow) => void; onSaveLocal?: (document: DocumentRow) => void; busy?: boolean }) {
  if (!rows.length) return <EmptyState title="文件匣目前是空的" detail="加入 PDF、JPG、PNG 或 CSV 文件開始整理。" />;
  return <ul className={expanded ? "document-list expanded" : "document-list"}>{rows.map((row) => {
    const isPdf = row.content_type.includes("pdf") || row.filename.toLowerCase().endsWith(".pdf");
    const hasLocal = row.sources?.some((source) => source.type === "local_file");
    const hasRemote = row.sources?.some((source) => source.type === "gmail_attachment");
    return <li key={row.id}><span className={`file-icon ${isPdf ? "pdf" : row.content_type.includes("image") ? "image" : "csv"}`}>{isPdf ? "PDF" : row.content_type.includes("image") ? "IMG" : "CSV"}</span><span className="file-info"><a href={api.documentUrl(row.id)} target="_blank" rel="noreferrer"><strong>{row.filename}</strong></a><small>{formatBytes(row.size_bytes)} · {new Date(row.created_at).toLocaleDateString("zh-TW")}{hasRemote ? " · Gmail" : ""}</small></span><span className="document-actions">{isPdf && onPreview && <button className="small-action" title="開啟 PDF 預覽" aria-label={`預覽 ${row.filename}`} onClick={() => onPreview(row)}>預覽</button>}{hasRemote && !hasLocal && onSaveLocal && <button className="small-action" title="將附件保存到本機文件匣" aria-label={`保存 ${row.filename} 到本機`} disabled={busy} onClick={() => onSaveLocal(row)}>保存</button>}</span><span className="file-state" title={hasLocal ? "本機已有副本" : "來自遠端文件來源"}>{hasLocal ? "✓" : hasRemote ? "↗" : "✓"}</span></li>;
  })}</ul>;
}

function JobList({ rows, expanded = false }: { rows: Job[]; expanded?: boolean }) {
  if (!rows.length) return <EmptyState title="還沒有匯入紀錄" detail="上傳文件或匯入 CSV 後，這裡會列出處理狀態。" />;
    return <div className={expanded ? "job-list expanded" : "job-list"}>{rows.map((job) => <div className="job-row" key={job.id}><span className="job-type">{job.source_type === "gmail_sync" ? "GMAIL" : job.source_type === "csv" ? "CSV" : "DOC"}</span><span className="job-info"><strong>{job.source_type === "gmail_sync" ? "Gmail 同步" : job.target_module === "finance" ? "財務資料匯入" : "文件匯入"}</strong><small>{job.summary} · {new Date(job.created_at).toLocaleString("zh-TW")}</small></span><span className={`job-status ${job.status}`}>{job.status === "completed" ? "完成" : job.status === "duplicate" ? "內容重複" : job.status === "partial" ? "部分完成" : job.status}</span></div>)}</div>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) { return <div className="empty-state"><span className="empty-mark">⌁</span><strong>{title}</strong><p>{detail}</p></div>; }
function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

function SettingsView({ report, onRefresh }: { report: (message: string, error?: string) => void; onRefresh: () => Promise<void> }) {
  const [secretProfiles, setSecretProfiles] = useState<SecretProfile[]>([]);
  const [documentProfiles, setDocumentProfiles] = useState<DocumentSecurityProfile[]>([]);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [ai, setAi] = useState<{ configured: boolean; provider: string | null; model: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [secret, setSecret] = useState({ display_name: "", national_id: "", birthday: "" });
  const [documentProfile, setDocumentProfile] = useState({ display_name: "", institution: "", sender_pattern: "", secret_profile_id: "" });
  const [aiConfig, setAiConfig] = useState({ api_key: "", model: "gpt-4.1-mini" });

  const load = useCallback(async () => {
    try {
      const [members, secureProfiles, gmailStatus, aiStatus] = await Promise.all([
        api.secretProfiles(), api.documentSecurityProfiles(), api.gmailStatus(), api.aiProvider(),
      ]);
      setSecretProfiles(members); setDocumentProfiles(secureProfiles); setGmail(gmailStatus); setAi(aiStatus); setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "無法讀取設定");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function createSecret(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api.createSecretProfile(secret);
      setSecret({ display_name: "", national_id: "", birthday: "" });
      await load(); report("家庭成員資料已安全保存到 Windows Credential Manager");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法保存家庭成員資料"); }
    finally { setBusy(false); }
  }

  async function createDocumentProfile(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api.createDocumentSecurityProfile({ ...documentProfile, sender_pattern: documentProfile.sender_pattern || null });
      setDocumentProfile({ display_name: "", institution: "", sender_pattern: "", secret_profile_id: "" });
      await load(); report("文件安全 profile 已建立");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法建立文件 profile"); }
    finally { setBusy(false); }
  }

  async function saveAi(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await api.configureAiProvider(aiConfig);
      setAiConfig((current) => ({ ...current, api_key: "" }));
      setAi({ configured: result.configured, provider: "openai", model: result.model });
      report("AI 設定已保存；只有預覽時勾選允許 AI 才會分析遮罩後的密碼說明");
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
      report(`Gmail 同步完成：新增附件 ${result.new_attachments} 份、交易 ${result.created_transactions} 筆、失敗 ${result.failures} 件${suffix}`);
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
    <div className="settings-layout">
      <section className="settings-section">
        <div className="settings-heading"><div><p className="eyebrow">本機保管</p><h2>家庭成員資料</h2><p>身分證字號與生日只存於 Windows 安全資料保管庫。</p></div></div>
        <form className="settings-form" onSubmit={(event) => void createSecret(event)}>
          <label>顯示名稱<input required maxLength={100} value={secret.display_name} onChange={(event) => setSecret({ ...secret, display_name: event.target.value })} /></label>
          <label>身分證字號<input required type="password" autoComplete="off" maxLength={64} value={secret.national_id} onChange={(event) => setSecret({ ...secret, national_id: event.target.value })} /></label>
          <label>出生日期<input required type="date" value={secret.birthday} onChange={(event) => setSecret({ ...secret, birthday: event.target.value })} /></label>
          <button className="button primary" disabled={busy || !secret.display_name || !secret.national_id || !secret.birthday}>安全保存</button>
        </form>
        <ul className="settings-list">{secretProfiles.map((profile) => <li key={profile.id}><strong>{profile.display_name}</strong><span>身分資料已保管</span></li>)}</ul>
      </section>

      <section className="settings-section">
        <div className="settings-heading"><div><p className="eyebrow">文件規則</p><h2>安全 profile</h2><p>將密碼規則與對應家庭成員資料連結。</p></div></div>
        <form className="settings-form" onSubmit={(event) => void createDocumentProfile(event)}>
          <label>Profile 名稱<input required maxLength={100} value={documentProfile.display_name} onChange={(event) => setDocumentProfile({ ...documentProfile, display_name: event.target.value })} /></label>
          <label>銀行或機構<input required maxLength={100} value={documentProfile.institution} onChange={(event) => setDocumentProfile({ ...documentProfile, institution: event.target.value })} /></label>
          <label>寄件者比對文字（選填）<input maxLength={255} value={documentProfile.sender_pattern} onChange={(event) => setDocumentProfile({ ...documentProfile, sender_pattern: event.target.value })} /></label>
          <label>家庭成員<select required value={documentProfile.secret_profile_id} onChange={(event) => setDocumentProfile({ ...documentProfile, secret_profile_id: event.target.value })}><option value="">選擇成員</option>{secretProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select></label>
          <button className="button primary" disabled={busy || secretProfiles.length === 0}>建立 profile</button>
        </form>
        <ul className="settings-list">{documentProfiles.map((profile) => <li key={profile.id}><strong>{profile.display_name}</strong><span>{profile.institution}</span></li>)}</ul>
      </section>

      <section className="settings-section">
        <div className="settings-heading"><div><p className="eyebrow">可選服務</p><h2>AI 密碼規則辨識</h2><p>AI 只收到遮罩後的密碼說明文字，不會收到身分證、生日或組合密碼。</p></div><span className={ai?.configured ? "connection-state ready" : "connection-state"}>{ai?.configured ? `已設定 · ${ai.model}` : "未設定"}</span></div>
        <form className="settings-form settings-form-two" onSubmit={(event) => void saveAi(event)}>
          <label>OpenAI API key<input required type="password" autoComplete="new-password" value={aiConfig.api_key} onChange={(event) => setAiConfig({ ...aiConfig, api_key: event.target.value })} placeholder={ai?.configured ? "已設定；輸入新 key 可更新" : "sk-..."} /></label>
          <label>模型<input required maxLength={120} value={aiConfig.model} onChange={(event) => setAiConfig({ ...aiConfig, model: event.target.value })} /></label>
          <button className="button secondary" disabled={busy || !aiConfig.api_key}>保存 AI 設定</button>
        </form>
      </section>

      <section className="settings-section">
        <div className="settings-heading"><div><p className="eyebrow">只讀連線</p><h2>Gmail 帳單</h2><p>預設搜尋全部可存取郵件（含垃圾郵件與封存），不設日期範圍；附件預設只保存來源參照。</p></div><span className={gmail?.authorized ? "connection-state ready" : "connection-state"}>{gmail?.authorized ? "已連線 · 唯讀" : gmail?.configured ? "待授權" : "未設定"}</span></div>
        {gmail && <p className="settings-note">同步狀態：{gmail.last_sync_status === "never" ? "尚未同步" : gmail.last_sync_status === "completed" ? "完成" : gmail.last_sync_status === "failed" ? "失敗" : gmail.last_sync_status === "running" ? "同步中" : "部分完成"}{gmail.last_successful_sync ? ` · 最近成功 ${new Date(gmail.last_successful_sync).toLocaleString("zh-TW")}` : ""}{gmail.last_error_summary ? ` · ${gmail.last_error_summary}` : ""}{gmail.full_sync_in_progress ? " · 初次同步尚在分批處理" : ""}</p>}
        <div className="gmail-actions"><label className="button secondary">選擇 OAuth 桌面設定<input type="file" accept="application/json,.json" disabled={busy} onChange={(event) => { void configureGmail(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label><button className="button secondary" disabled={busy || !gmail?.configured} onClick={() => void authorizeGmail()}>連接 Google 帳戶</button><button className="button primary" disabled={busy || !gmail?.authorized} onClick={() => void syncGmail()}>{busy ? "處理中…" : "立即同步 Gmail"}</button></div>
        {gmail && <div className="gmail-schedule"><label><input type="checkbox" checked={gmail.auto_sync_enabled} disabled={busy || !gmail.authorized} onChange={(event) => void setGmailSchedule(event.target.checked)} /><span>啟用每 {gmail.sync_interval_minutes} 分鐘自動同步</span></label>{gmail.auto_sync_enabled && gmail.next_sync_at && <span className="settings-note">下次同步：{new Date(gmail.next_sync_at).toLocaleString("zh-TW")}</span>}</div>}
        <p className="settings-note">請先在 Google Cloud 建立 OAuth 用戶端 ID，應用程式類型選「桌面應用程式」，啟用 Gmail API，下載 JSON 後於此選取。連線只要求 gmail.readonly 權限。</p>
      </section>
    </div>
  </>;
}

function PdfPreviewDialog({ document, onClose }: { document: DocumentRow; onClose: () => void }) {
  const [profiles, setProfiles] = useState<DocumentSecurityProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [allowAi, setAllowAi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const [extractionStatus, setExtractionStatus] = useState("");

  useEffect(() => { void api.documentSecurityProfiles().then(setProfiles).catch(() => setProfiles([])); }, []);
  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  async function preview(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await api.preview(document.id, {
        document_security_profile_id: profileId,
        subject,
        body,
        allow_ai_analysis: allowAi,
      });
      setPdfUrl(URL.createObjectURL(result.blob));
      setExtractionStatus(result.extraction ?? "");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "無法預覽 PDF"); }
    finally { setBusy(false); }
  }

  return <div className="preview-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="preview-dialog" role="dialog" aria-modal="true" aria-labelledby="preview-title">
      <header className="preview-header"><div><p className="eyebrow">文件預覽</p><h2 id="preview-title">{document.filename}</h2></div><button className="icon-button" aria-label="關閉預覽" title="關閉預覽" onClick={onClose}>×</button></header>
      <div className="preview-body">
        <form className="preview-controls" onSubmit={(event) => void preview(event)}>
          <label>文件安全 profile<select value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">不使用密碼資料</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name} · {profile.institution}</option>)}</select></label>
          <label>郵件主旨（選填）<input maxLength={500} value={subject} onChange={(event) => setSubject(event.target.value)} /></label>
          <label>密碼規則說明<textarea rows={8} maxLength={20_000} value={body} onChange={(event) => setBody(event.target.value)} placeholder="例如：密碼為身分證末四碼加出生日期 YYYYMMDD" /></label>
          <label className="check-row"><input type="checkbox" checked={allowAi} onChange={(event) => setAllowAi(event.target.checked)} /><span>允許 AI 分析遮罩後的規則文字</span></label>
          <button className="button primary" disabled={busy}>{busy ? "正在處理…" : "產生預覽"}</button>
          <p className="settings-note">解密只在本機暫存處理；原始 PDF 不變。未勾選時只使用已驗證的規則，不會呼叫 AI。</p>
          {error && <div className="notice error" role="alert">{error}</div>}
          {extractionStatus === "unavailable" && <div className="notice info" role="status">此 PDF 需要本機 OCR，但引擎尚未就緒；請確認 Tesseract 與 PDFium 依賴，仍可檢視頁面。</div>}
          {extractionStatus === "language_unavailable" && <div className="notice info" role="status">Tesseract 找不到設定所需的語言資料；請檢查 FAMILY_FINANCE_HUB_OCR_LANG 與語言資料安裝，仍可檢視頁面。</div>}
          {extractionStatus === "failed" && <div className="notice info" role="status">OCR 處理未完成，仍可檢視頁面。</div>}
          {extractionStatus === "partial" && <div className="notice info" role="status">OCR 只完成部分頁面，仍可檢視完整 PDF。</div>}
          {extractionStatus === "insufficient" && <div className="notice info" role="status">OCR 已執行，但未取得足夠文字；仍可檢視頁面。</div>}
        </form>
        <div className="pdf-stage">{pdfUrl ? <iframe title={`PDF 預覽：${document.filename}`} src={pdfUrl} /> : <EmptyState title="尚未產生預覽" detail="選擇設定後開始檢視這份 PDF。" />}</div>
      </div>
    </section>
  </div>;
}
