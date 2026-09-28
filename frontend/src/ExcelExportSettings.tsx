import { useEffect, useState } from "react";
import { api, type WorkbookExportStatus } from "./api";

export function ExcelExportSettings() {
  const [status, setStatus] = useState<WorkbookExportStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (busy) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api.workbookStatus();
        if (active) { setStatus(result); setError(""); }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "無法讀取 Excel 狀態");
      } finally {
        if (active) timer = setTimeout(() => void poll(), 5000);
      }
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [busy]);

  async function update(enabled?: boolean) {
    setBusy(true); setError("");
    try {
      setStatus(await (enabled === undefined ? api.refreshWorkbook() : api.configureWorkbook(enabled)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Excel 更新失敗");
    } finally { setBusy(false); }
  }

  const ready = status?.file_available && !status.needs_update;
  return <div className="excel-settings">
    <div className="settings-heading">
      <div><h2>Excel 自動更新</h2></div>
      <span className={ready ? "connection-state ready" : "connection-state"}>
        {busy ? "更新中" : status?.last_error ? "待重試" : ready ? "已更新" : "尚未更新"}
      </span>
    </div>
    {error && <div className="notice error" role="alert">{error}</div>}
    {!status && !error && <p role="status">讀取 Excel 設定中…</p>}
    {status && <>
      <label className="check-row excel-toggle">
        <input type="checkbox" checked={status.enabled} disabled={busy} onChange={(event) => void update(event.target.checked)} />
        <span>自動更新專用 Excel</span>
      </label>
      <dl className="excel-status-grid">
        <div><dt>已匯出交易</dt><dd>{status.exported_transactions} 筆</dd></div>
        <div><dt>PDF 尚未入帳</dt><dd>{status.pending_pdf_documents} 份</dd></div>
        <div><dt>最近更新</dt><dd>{status.last_successful_at ? new Date(status.last_successful_at).toLocaleString("zh-TW") : "尚未產生"}</dd></div>
      </dl>
      <p className="excel-path"><span>儲存位置</span><code>{status.output_path}</code></p>
      {status.last_error && <div className="notice error" role="alert">{status.last_error}{status.enabled ? "系統會自動重試。" : "自動更新目前已關閉。"}</div>}
      {!status.pdf_transaction_parser_ready && <p className="notice info">PDF 交易解析尚未啟用；目前 Excel 只包含已入帳交易。</p>}
      <p className="settings-note">啟用後每 {status.check_interval_seconds} 秒檢查資料變更。撤銷帳單也會更新；直接編輯這份 Excel 的內容會在下次更新時被取代。</p>
      <div className="gmail-actions">
        <button className="button secondary" disabled={busy} onClick={() => void update()}>{busy ? "更新中…" : "立即更新 Excel"}</button>
        {ready && <a className="button secondary" href={api.workbookUrl} download>下載 Excel</a>}
      </div>
    </>}
  </div>;
}
