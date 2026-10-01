import { useCallback, useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { api, type Category, type CategorySpending } from "../api";
import { CategoryDonut } from "./CategoryDonut";
import { CategoryDetailPanel } from "./CategoryDetailPanel";
import { UncategorizedReview } from "./UncategorizedReview";
import { donutSlices, formatMoney, type ChartSlice } from "./chart";

function selection() { const params = new URLSearchParams(window.location.search); return { category: params.get("category"), merchant: params.get("merchant") }; }
export function SpendingByCategory({ month, currency, currencies, version, onChanged, onOpenDocument }: { month: string; currency: string; currencies: string[]; version: number; onChanged: () => void | Promise<void>; onOpenDocument: (id: string) => void }) {
  const [localCurrency, setLocalCurrency] = useState("TWD");
  const chosenCurrency = currency || (currencies.includes(localCurrency) ? localCurrency : currencies[0] || "TWD");
  const [data, setData] = useState<CategorySpending | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [selected, setSelected] = useState(selection);
  const [review, setReview] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => { const listener = () => setSelected(selection()); window.addEventListener("popstate", listener); return () => window.removeEventListener("popstate", listener); }, []);
  useEffect(() => {
    let active = true; setLoading(true); setData(null); setError(""); setSelected(selection());
    Promise.all([api.spendingByCategory(month, chosenCurrency), api.categories()]).then(([spending, list]) => { if (active) { setData(spending); setCategories(list); } }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法載入分類支出"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [month, chosenCurrency, version, retry]);
  const select = useCallback((category: string | null, merchant: string | null = null) => {
    const url = new URL(window.location.href);
    if (category) { url.searchParams.set("category", category); url.searchParams.set("currency", chosenCurrency); url.searchParams.set("month", month); }
    else { url.searchParams.delete("category"); if (!currency) url.searchParams.delete("currency"); }
    if (merchant !== null) url.searchParams.set("merchant", merchant); else url.searchParams.delete("merchant");
    window.history.pushState({}, "", url.pathname + url.search); setSelected({ category, merchant });
  }, [chosenCurrency, month, currency]);
  const category = data?.categories.find(item => item.category_id === selected.category);
  const uncategorized = data?.categories.find(item => item.code === "uncategorized");
  const other = data ? donutSlices(data.categories).find(item => item.id === "__other__") : null;
  const chooseSlice = (slice: ChartSlice) => { if (slice.code === "uncategorized") { select(null); setReview(true); } else { setReview(false); select(slice.id); } };
  return <section className="category-spending" aria-label="分類支出">
    <div className="category-heading"><div><h2>分類支出</h2><span>{month} · {chosenCurrency}</span></div><div className="category-actions">{!currency && <select aria-label="分類支出幣別" value={chosenCurrency} onChange={event => { setLocalCurrency(event.target.value); select(null); }}>{(currencies.length ? currencies : ["TWD"]).map(code => <option key={code}>{code}</option>)}</select>}<button className="text-button" aria-expanded={review} onClick={() => setReview(!review)}>待分類商家</button></div></div>
    {loading && <p role="status">載入分類支出…</p>}{error && <div className="category-error" role="alert">{error}<button className="text-button" onClick={() => setRetry(retry + 1)}>重試</button></div>}
    {data && <><div className="category-summary"><span>期間淨支出<strong>{formatMoney(data.dashboard_expense, chosenCurrency)}</strong></span><span>正淨支出<strong>{formatMoney(data.positive_category_total, chosenCurrency)}</strong></span><span>退款／抵扣<strong>{formatMoney(data.refund_credit_total, chosenCurrency)}</strong></span></div>
      <CategoryDonut categories={data.categories} currency={chosenCurrency} onSelect={chooseSlice} />
      {!!uncategorized?.transaction_count && <div className="category-pending"><span>{uncategorized.transaction_count} 筆支出待分類</span><button className="text-button" aria-expanded={review} onClick={() => { select(null); setReview(!review); }}>整理分類<ChevronRight size={16} /></button></div>}
      {!!data.negative_categories.length && <div className="category-refunds"><h3>退款／抵扣</h3>{data.negative_categories.map(item => <button className="text-button" key={item.category_id} onClick={() => select(item.category_id)}>{item.name}<strong>{formatMoney(item.net_amount, chosenCurrency)}</strong><ChevronRight size={16} /></button>)}</div>}
      {selected.category === "__other__" && other && <section className="category-other"><h3>其餘類別</h3>{other.categories.map(item => <button className="text-button" key={item.category_id} onClick={() => select(item.category_id)}>{item.name}<strong>{formatMoney(item.net_amount, chosenCurrency)}</strong><ChevronRight size={16} /></button>)}</section>}
      {category && <CategoryDetailPanel category={category} month={month} currency={chosenCurrency} categories={categories} version={version} merchantKey={selected.merchant} onMerchant={key => select(category.category_id, key)} onClose={() => select(null)} onChanged={onChanged} onOpenDocument={onOpenDocument} />}
      {review && <UncategorizedReview month={month} currency={chosenCurrency} categories={categories} version={version} onChanged={onChanged} onOpenDocument={onOpenDocument} />}
    </>}
  </section>;
}
