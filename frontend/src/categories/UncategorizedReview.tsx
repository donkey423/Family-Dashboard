import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { api, type Category, type CategoryMerchant } from "../api";
import { CategoryDetailPanel } from "./CategoryDetailPanel";
import { formatMoney } from "./chart";

export function UncategorizedReview({ month, currency, categories, version, onChanged, onOpenDocument }: { month: string; currency: string; categories: Category[]; version: number; onChanged: () => void | Promise<void>; onOpenDocument?: (id: string) => void }) {
  const [rows, setRows] = useState<CategoryMerchant[]>([]);
  const [selected, setSelected] = useState<CategoryMerchant | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => { setSelected(null); }, [month, currency]);
  useEffect(() => {
    let active = true; setRows([]); setLoading(true); setError("");
    api.uncategorizedMerchants(month, currency).then(value => { if (active) setRows(value.items); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法載入未分類商家"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [month, currency, version]);
  const unknown = categories.find(item => item.code === "uncategorized");
  return <section className="category-review"><h3>待分類商家</h3>{loading && <p role="status">載入中…</p>}{error && <p role="alert" className="category-error">{error}</p>}{!loading && !error && !selected && <ul className="category-merchant-list">{rows.map(row => <li key={row.merchant_key}><button className="category-merchant-link" title={`分類 ${row.display_name}`} aria-label={`分類 ${row.display_name}`} onClick={() => setSelected(row)}><span>{row.display_name}<small>{row.transaction_count} 筆 · {formatMoney(row.net_amount, currency)}</small></span><ChevronRight size={16} /></button></li>)}{!rows.length && <li>本期支出皆已分類</li>}</ul>}
    {selected && <CategoryDetailPanel key={`${month}/${currency}/${selected.merchant_key}`} category={{ category_id: unknown?.id ?? "uncategorized", code: "uncategorized", name: "未分類", net_amount: selected.net_amount, transaction_count: selected.transaction_count }} month={month} currency={currency} categories={categories} version={version} merchantKey={selected.merchant_key} onMerchant={() => setSelected(null)} onClose={() => setSelected(null)} onChanged={onChanged} onOpenDocument={onOpenDocument} />}
  </section>;
}
