import { useEffect, useRef, useState } from "react";
import { Save, Undo2, X } from "lucide-react";
import { api, type Category, type CategoryImpact, type Transaction } from "../api";
import { formatMoney } from "./chart";
import { useDialogFocus } from "../useDialogFocus";

export function CategoryPicker({ transaction, categories, onClose, onChanged, defaultScope = "transaction" }: { transaction: Transaction; categories: Category[]; onClose: () => void; onChanged: () => void | Promise<void>; defaultScope?: "transaction" | "merchant" }) {
  const dialog = useRef<HTMLDivElement>(null);
  const [category, setCategory] = useState(transaction.category_id ?? "uncategorized");
  const [scope, setScope] = useState(defaultScope);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [impact, setImpact] = useState<CategoryImpact | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setImpact(null); setError("");
    if (scope !== "merchant") { setPreviewing(false); return; }
    setPreviewing(true);
    api.categoryImpact(transaction.id, category).then(value => { if (active) setImpact(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法預覽影響"); })
      .finally(() => { if (active) setPreviewing(false); });
    return () => { active = false; };
  }, [transaction.id, category, scope, retry]);
  useDialogFocus(dialog, () => { if (!busy) onClose(); });
  async function save(clear = false) {
    setBusy(true); setError("");
    try {
      if (clear) await api.clearCategoryOverride(transaction.id);
      else if (scope === "merchant") await api.assignCategory(transaction.id, category, scope, impact?.impact_token);
      else await api.assignCategory(transaction.id, category, scope);
      await onChanged(); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "分類更新失敗"); if (scope === "merchant") setImpact(null); }
    finally { setBusy(false); }
  }
  return <div className="category-modal-backdrop"><div className="category-modal" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="category-picker-title" tabIndex={-1}>
    <div className="category-heading"><h2 id="category-picker-title">修改分類</h2><button className="icon-button" title="關閉" aria-label="關閉分類" disabled={busy} onClick={onClose}><X size={18} /></button></div>
    <p className="category-description">{transaction.description}</p>
    <p>{transaction.date ?? "未提供日期"} · {formatMoney(transaction.amount, transaction.currency)}</p>
    {transaction.category_reason && <p className="category-description">本機分類依據：{transaction.category_reason}</p>}
    <label>分類<select aria-label="分類" value={category} disabled={busy} onChange={event => setCategory(event.target.value)} data-dialog-initial-focus>{categories.filter(item => item.is_active).map(item => <option value={item.id} key={item.id}>{item.display_name}</option>)}</select></label>
    <fieldset disabled={busy}><legend>套用範圍</legend><label><input type="radio" name="scope" checked={scope === "transaction"} onChange={() => setScope("transaction")} />僅此筆交易</label><label><input type="radio" name="scope" checked={scope === "merchant"} onChange={() => setScope("merchant")} />此商家的現在與未來交易</label></fieldset>
    {scope === "merchant" && <div className="category-impact">{previewing && <p role="status">預覽跨月份影響…</p>}{impact && <><p>將改變 {impact.changed_count} 筆既有交易；保留 {impact.protected_override_count} 筆單筆指定。</p><p>影響月份：{impact.months.join("、") || "沒有既有分類變更"}</p><p>未來相同商家也會套用此分類。</p></>}{!previewing && !impact && <button className="text-button" disabled={busy} onClick={() => setRetry(value => value + 1)}>重新預覽影響</button>}</div>}
    {error && <p role="alert" className="category-error">{error}</p>}
    <div className="category-actions">{transaction.category_source === "override" && <button className="text-button" disabled={busy} onClick={() => void save(true)}><Undo2 size={16} />恢復規則分類</button>}<button className="button primary" disabled={busy || !category || (scope === "merchant" && (!impact || previewing))} onClick={() => void save()}><Save size={16} />{busy ? "儲存中…" : "儲存"}</button></div>
  </div></div>;
}
