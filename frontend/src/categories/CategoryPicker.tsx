import { useRef, useState } from "react";
import { Save, Undo2, X } from "lucide-react";
import { api, type Category, type Transaction } from "../api";
import { useDialogFocus } from "../useDialogFocus";

export function CategoryPicker({ transaction, categories, onClose, onChanged, defaultScope = "transaction" }: { transaction: Transaction; categories: Category[]; onClose: () => void; onChanged: () => void | Promise<void>; defaultScope?: "transaction" | "merchant" }) {
  const dialog = useRef<HTMLDivElement>(null);
  const [category, setCategory] = useState(transaction.category_id ?? "uncategorized");
  const [scope, setScope] = useState(defaultScope);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useDialogFocus(dialog, () => { if (!busy) onClose(); });
  async function save(clear = false) {
    setBusy(true); setError("");
    try {
      if (clear) await api.clearCategoryOverride(transaction.id);
      else await api.assignCategory(transaction.id, category, scope);
      await onChanged(); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "分類更新失敗"); }
    finally { setBusy(false); }
  }
  return <div className="category-modal-backdrop"><div className="category-modal" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="category-picker-title" tabIndex={-1}>
    <div className="category-heading"><h2 id="category-picker-title">修改分類</h2><button className="icon-button" title="關閉" aria-label="關閉分類" disabled={busy} onClick={onClose}><X size={18} /></button></div>
    <p className="category-description">{transaction.description}</p>
    <label>分類<select aria-label="分類" value={category} disabled={busy} onChange={event => setCategory(event.target.value)} data-dialog-initial-focus>{categories.filter(item => item.is_active).map(item => <option value={item.id} key={item.id}>{item.display_name}</option>)}</select></label>
    <fieldset disabled={busy}><legend>套用範圍</legend><label><input type="radio" name="scope" checked={scope === "transaction"} onChange={() => setScope("transaction")} />僅此筆交易</label><label><input type="radio" name="scope" checked={scope === "merchant"} onChange={() => setScope("merchant")} />此商家的現在與未來交易</label></fieldset>
    {error && <p role="alert" className="category-error">{error}</p>}
    <div className="category-actions">{transaction.category_source === "override" && <button className="text-button" disabled={busy} onClick={() => void save(true)}><Undo2 size={16} />恢復規則分類</button>}<button className="button primary" disabled={busy || !category} onClick={() => void save()}><Save size={16} />{busy ? "儲存中…" : "儲存"}</button></div>
  </div></div>;
}
