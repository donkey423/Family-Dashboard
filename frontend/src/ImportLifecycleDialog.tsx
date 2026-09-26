import { useEffect, useRef, useState } from "react";
import { api, type DocumentRow, type ImportImpact } from "./api";

type Props = {
  document: DocumentRow;
  onClose: () => void;
  onChanged: (result: ImportImpact & { changed: boolean }) => Promise<void>;
};

export function ImportLifecycleDialog({ document, onClose, onChanged }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [impact, setImpact] = useState<ImportImpact | null>(null);
  const [reason, setReason] = useState("誤匯入帳單");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const restoring = document.revoked_at !== null;
  const action = restoring ? "恢復" : "撤銷";
  const alreadyDone = impact !== null && (restoring ? impact.revoked_at === null : impact.revoked_at !== null);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true); setImpact(null); setError("");
    api.importImpact(document.id)
      .then((result) => { if (active) setImpact(result); })
      .catch((failure) => { if (active) setError(failure instanceof Error ? failure.message : "無法載入影響範圍"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [document.id, retry]);

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (!impact || busy || alreadyDone) return;
    setBusy(true); setError("");
    try {
      const result = await api.changeImportState(document.id, restoring ? "restore" : "revoke", impact.impact_token, restoring ? "" : reason);
      await onChanged(result);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : `${action}失敗`);
      setImpact(null);
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="lifecycle-dialog" aria-labelledby="lifecycle-title" aria-describedby="lifecycle-consequence"
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <form onSubmit={(event) => void confirm(event)}>
      <header><h2 id="lifecycle-title">{action}文件匯入</h2><p className="lifecycle-filename">{document.filename}</p></header>
      <p id="lifecycle-consequence" className="lifecycle-consequence">{restoring
        ? "關聯交易將重新計入收支。只恢復原有紀錄，不會重新解析文件。"
        : "關聯交易將退出收支統計、交易列表與搜尋。原始文件與交易保留，可隨時恢復。"}</p>
      {loading && <p role="status">正在確認影響範圍…</p>}
      {error && <div className="notice error" role="alert">{error}</div>}
      {!impact && !loading && <button className="small-action" type="button" disabled={busy} onClick={() => setRetry((value) => value + 1)}>重新檢視影響</button>}
      {impact && <>
        <div className="impact-count"><span>關聯交易</span><strong>{impact.transaction_count} <small>筆</small></strong></div>
        {impact.currency_totals.length > 0 && <div className="impact-totals" aria-label="受影響金額">
          {impact.currency_totals.map((total) => <section key={total.currency}>
            <h3>{total.currency}</h3><dl>
              <div><dt>收入</dt><dd>{total.income}</dd></div>
              <div><dt>支出</dt><dd>{total.expenses}</dd></div>
              <div><dt>淨額</dt><dd>{total.net}</dd></div>
            </dl>
          </section>)}
        </div>}
        {impact.transaction_count === 0 && <p className="lifecycle-note">這份文件目前沒有交易紀錄，收支金額不變。</p>}
        {impact.revocation_reason && <p className="lifecycle-note">撤銷原因：{impact.revocation_reason}</p>}
        {alreadyDone ? <p role="status" className="notice info">此文件已{action}，不需要再次操作。</p> : !restoring && <label className="lifecycle-reason">撤銷原因<select value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)}>
          <option>誤匯入帳單</option><option>重複帳單</option><option>內容不正確</option><option>其他</option>
        </select></label>}
        {!restoring && !alreadyDone && <p className="lifecycle-note">相同內容再次上傳或從 Gmail 同步，仍會保持已撤銷。</p>}
      </>}
      <footer><button className="button secondary" type="button" autoFocus disabled={busy} onClick={onClose}>{alreadyDone ? "關閉" : "取消"}</button>
        <button className={`button ${restoring ? "primary" : "danger"}`} disabled={!impact || loading || busy || alreadyDone}>{busy ? "處理中…" : `確認${action}`}</button></footer>
    </form>
  </dialog>;
}
