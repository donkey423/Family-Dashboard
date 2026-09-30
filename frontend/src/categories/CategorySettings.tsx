import { useEffect, useState } from "react";
import { Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { api, type Category, type CategoryRule } from "../api";

export function CategorySettings() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<CategoryRule[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [editing, setEditing] = useState<Category | null>(null);
  const [editName, setEditName] = useState("");
  const [pattern, setPattern] = useState("");
  const [type, setType] = useState<"normalized_exact" | "contains">("normalized_exact");
  const [target, setTarget] = useState("food");
  const [priority, setPriority] = useState(0);
  const [editingRule, setEditingRule] = useState<CategoryRule | null>(null);
  const [editPattern, setEditPattern] = useState("");
  const [editPriority, setEditPriority] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([api.categories(), api.categoryRules()]).then(([list, rules]) => { if (active) { setCategories(list); setRules(rules); } }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法載入分類設定"); });
    return () => { active = false; };
  }, [revision]);
  async function mutate(action: () => Promise<unknown>, done?: () => void) {
    setBusy(true); setError("");
    try { await action(); done?.(); setRevision(value => value + 1); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "分類設定更新失敗"); }
    finally { setBusy(false); }
  }
  return <div className="category-settings">
    <h2>消費分類</h2>{error && <div className="category-error" role="alert">{error}<button className="text-button" onClick={() => { setError(""); setRevision(value => value + 1); }}>重試</button></div>}
    <form className="category-form" onSubmit={event => { event.preventDefault(); void mutate(() => api.createCategory({ code, display_name: name }), () => { setName(""); setCode(""); }); }}>
      <label>分類名稱<input aria-label="新分類名稱" maxLength={100} required value={name} onChange={event => setName(event.target.value)} /></label><label>分類代碼<input aria-label="新分類代碼" pattern="[a-z][a-z0-9_]*" maxLength={80} required value={code} onChange={event => setCode(event.target.value)} /></label><button className="button" disabled={busy} type="submit"><Plus size={16} />新增分類</button>
    </form>
    <ul className="category-settings-list">{categories.map(item => <li key={item.id}><span>{item.display_name}<small>{item.code}</small></span><div className="category-actions"><button className="icon-button" title={`重新命名 ${item.display_name}`} aria-label={`重新命名 ${item.display_name}`} disabled={busy} onClick={() => { setEditing(item); setEditName(item.display_name); }}><Pencil size={16} /></button><label><input type="checkbox" aria-label={`啟用 ${item.display_name}`} checked={item.is_active} disabled={busy || ["uncategorized", "income", "transfer"].includes(item.code)} onChange={event => void mutate(() => api.updateCategory(item.id, { is_active: event.target.checked }))} />啟用</label></div></li>)}</ul>
    {editing && <form className="category-form" onSubmit={event => { event.preventDefault(); void mutate(() => api.updateCategory(editing.id, { display_name: editName }), () => setEditing(null)); }}><label>分類名稱<input aria-label="修改分類名稱" required maxLength={100} value={editName} onChange={event => setEditName(event.target.value)} /></label><button className="icon-button" title="儲存名稱" aria-label="儲存名稱" disabled={busy}><Save size={18} /></button><button className="icon-button" title="取消重新命名" aria-label="取消重新命名" type="button" disabled={busy} onClick={() => setEditing(null)}><X size={18} /></button></form>}
    <h3>商家規則</h3><form className="category-form" onSubmit={event => { event.preventDefault(); void mutate(() => api.createCategoryRule({ category_id: target, match_type: type, pattern, priority, enabled: true }), () => setPattern("")); }}>
      <label>商家文字<input aria-label="商家規則文字" value={pattern} maxLength={500} required onChange={event => setPattern(event.target.value)} /></label><label>比對<select aria-label="規則比對方式" value={type} onChange={event => setType(event.target.value as typeof type)}><option value="normalized_exact">完整商家名稱</option><option value="contains">包含文字</option></select></label><label>分類<select aria-label="規則分類" value={target} onChange={event => setTarget(event.target.value)}>{categories.filter(item => item.is_active).map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label><label>優先順序<input aria-label="規則優先順序" type="number" min={-100000} max={100000} value={priority} onChange={event => setPriority(Number(event.target.value))} /></label><button className="button" disabled={busy}><Plus size={16} />新增規則</button>
    </form>
    {editingRule && <form className="category-form" onSubmit={event => { event.preventDefault(); void mutate(() => api.updateCategoryRule(editingRule.id, { pattern: editPattern, priority: editPriority }), () => setEditingRule(null)); }}>
      <label>商家文字<input aria-label="修改商家規則文字" required maxLength={500} value={editPattern} onChange={event => setEditPattern(event.target.value)} /></label>
      <label>優先順序<input aria-label="修改規則優先順序" type="number" min={-100000} max={100000} value={editPriority} onChange={event => setEditPriority(Number(event.target.value))} /></label>
      <button className="icon-button" title="儲存規則" aria-label="儲存規則" disabled={busy}><Save size={18} /></button>
      <button className="icon-button" title="取消修改規則" aria-label="取消修改規則" type="button" disabled={busy} onClick={() => setEditingRule(null)}><X size={18} /></button>
    </form>}
    <ul className="category-settings-list">{rules.map(rule => <li key={rule.id}><span>{rule.pattern}<small>{rule.match_type === "contains" ? "包含" : "完整"} · 優先 {rule.priority}</small></span><div className="category-actions">
      <button className="icon-button" title={`修改規則 ${rule.pattern}`} aria-label={`修改規則 ${rule.pattern}`} disabled={busy} onClick={() => { setEditingRule(rule); setEditPattern(rule.pattern); setEditPriority(rule.priority); }}><Pencil size={16} /></button>
      <select aria-label={`規則 ${rule.pattern} 分類`} disabled={busy} value={rule.category_id} onChange={event => void mutate(() => api.updateCategoryRule(rule.id, { category_id: event.target.value }))}>{categories.map(item => <option key={item.id} value={item.id} disabled={!item.is_active}>{item.display_name}</option>)}</select><label><input type="checkbox" checked={rule.enabled} aria-label={`啟用規則 ${rule.pattern}`} disabled={busy} onChange={event => void mutate(() => api.updateCategoryRule(rule.id, { enabled: event.target.checked }))} />啟用</label><button className="icon-button" title={`刪除規則 ${rule.pattern}`} aria-label={`刪除規則 ${rule.pattern}`} disabled={busy} onClick={() => void mutate(() => api.deleteCategoryRule(rule.id))}><Trash2 size={16} /></button></div></li>)}{!rules.length && <li>尚無商家規則</li>}</ul>
  </div>;
}
