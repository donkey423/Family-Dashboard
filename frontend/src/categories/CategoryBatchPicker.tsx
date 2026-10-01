import { useEffect, useRef, useState } from "react";
import { Save, X } from "lucide-react";
import { api, type Category, type CategoryBatchImpact, type Transaction } from "../api";
import { useDialogFocus } from "../useDialogFocus";
import { formatMoney } from "./chart";

export function CategoryBatchPicker({ transactions, categories, onClose, onChanged }: {
  transactions: Transaction[]; categories: Category[]; onClose: () => void; onChanged: () => void | Promise<void>;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const [category, setCategory] = useState("");
  const [impact, setImpact] = useState<CategoryBatchImpact | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useDialogFocus(dialog, () => { if (!busy) onClose(); });
  useEffect(() => {
    let active = true; setImpact(null); setError("");
    if (!category) { setPreviewing(false); return; }
    setPreviewing(true);
    api.categoryBatchImpact(transactions.map(row => row.id), category)
      .then(value => { if (active) setImpact(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法預覽批次分類"); })
      .finally(() => { if (active) setPreviewing(false); });
    return () => { active = false; };
  }, [transactions, category, retry]);
  async function save() {
    if (!impact) return;
    setBusy(true); setError("");
    try {
      await api.assignCategoryBatch(transactions.map(row => row.id), category, impact.impact_token);
      await onChanged(); onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批次分類更新失敗"); setImpact(null);
    } finally { setBusy(false); }
  }
  return <div className="category-modal-backdrop"><div className="category-modal" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="category-batch-title" tabIndex={-1}>
    <div className="category-heading"><h2 id="category-batch-title">批次分類</h2><button className="icon-button" title="關閉" aria-label="關閉批次分類" disabled={busy} onClick={onClose}><X size={18} /></button></div>
    <label>分類<select aria-label="批次分類目標" value={category} disabled={busy} onChange={event => setCategory(event.target.value)} data-dialog-initial-focus><option value="">選擇分類</option>{categories.filter(item => item.is_active).map(item => <option value={item.id} key={item.id}>{item.display_name}</option>)}</select></label>
    <ul className="category-batch-rows">{(impact?.items ?? transactions).map(row => <li key={row.id}><strong>{row.description}</strong><span>{row.date ?? "未提供日期"} · {formatMoney(row.amount, row.currency)}</span><span>{row.category_name ?? "未分類"}{"protected_override" in row && row.protected_override ? " · 保留單筆指定" : ""}</span></li>)}</ul>
    {previewing && <p role="status">預覽批次影響…</p>}
    {impact && <div className="category-impact"><p>將修改 {impact.changed_count} 筆；保留 {impact.protected_override_count} 筆單筆指定。</p><p>影響月份：{impact.months.join("、") || "沒有分類變更"}</p><p>只套用所選交易，不建立商家規則。</p></div>}
    {error && <p role="alert" className="category-error">{error}</p>}
    <div className="category-actions">{category && !impact && !previewing && <button className="text-button" disabled={busy} onClick={() => setRetry(value => value + 1)}>重新預覽影響</button>}<button className="button primary" disabled={busy || previewing || !impact || impact.changed_count === 0} onClick={() => void save()}><Save size={16} />{busy ? "儲存中…" : "確認批次分類"}</button></div>
  </div></div>;
}
