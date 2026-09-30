import { useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { api, type Category, type CategoryMerchant } from "../api";
import { CategoryPicker } from "./CategoryPicker";
import { formatMoney } from "./chart";

export function UncategorizedReview({ month, currency, categories, version, onChanged }: { month: string; currency: string; categories: Category[]; version: number; onChanged: () => void | Promise<void> }) {
  const [rows, setRows] = useState<CategoryMerchant[]>([]);
  const [selected, setSelected] = useState<CategoryMerchant | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true; setRows([]); setLoading(true); setError("");
    api.uncategorizedMerchants(month, currency).then(value => { if (active) setRows(value.items); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法載入未分類商家"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [month, currency, version]);
  return <section className="category-review"><h3>待分類商家</h3>{loading && <p role="status">載入中…</p>}{error && <p role="alert" className="category-error">{error}</p>}{!loading && !error && <ul className="category-merchant-list">{rows.map(row => <li key={row.merchant_key}><span className="category-merchant-name">{row.display_name}<small>{row.transaction_count} 筆 · {formatMoney(row.net_amount, currency)}</small></span><button className="icon-button" title={`分類 ${row.display_name}`} aria-label={`分類 ${row.display_name}`} onClick={() => setSelected(row)}><Pencil size={16} /></button></li>)}{!rows.length && <li>本期支出皆已分類</li>}</ul>}
    {selected && <CategoryPicker categories={categories} transaction={{ id: selected.transaction_id, description: selected.display_name, category_id: "uncategorized", currency, amount: selected.net_amount, date: null, source_document_id: "" }} defaultScope="merchant" onClose={() => setSelected(null)} onChanged={onChanged} />}
  </section>;
}
