import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, Pencil, X } from "lucide-react";
import { api, type Category, type CategoryMerchant, type CategoryTotal, type Transaction, type TransactionPage } from "../api";
import { TransactionTable } from "../TransactionTable";
import { CategoryPicker } from "./CategoryPicker";
import { formatMoney } from "./chart";

export function CategoryDetailPanel({ category, month, currency, categories, version, merchantKey, onMerchant, onClose, onChanged, onOpenDocument }: { category: CategoryTotal; month: string; currency: string; categories: Category[]; version: number; merchantKey: string | null; onMerchant: (key: string | null) => void; onClose: () => void; onChanged: () => void | Promise<void>; onOpenDocument: (id: string) => void }) {
  const [merchants, setMerchants] = useState<CategoryMerchant[]>([]);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<TransactionPage | null>(null);
  const [picker, setPicker] = useState<Transaction | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => { setPage(0); }, [category.category_id, month, currency, merchantKey]);
  useEffect(() => {
    let active = true; setLoading(true); setError(""); setResult(null); setMerchants([]);
    const request = merchantKey === null
      ? api.categoryMerchants(month, currency, category.category_id).then(value => { if (active) setMerchants(value.items); })
      : api.transactions({ month, currency, category_id: category.category_id, merchant_key: merchantKey, consumption_only: true, limit: 50, offset: page * 50 }).then(value => { if (active) setResult(value); });
    request.catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "無法載入分類明細"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [category.category_id, month, currency, merchantKey, page, version]);
  return <section className="category-detail" aria-label="分類明細">
    <div className="category-heading"><div><h3>{category.name}</h3><span>{formatMoney(category.net_amount, currency)} · {category.transaction_count} 筆</span></div><div className="category-actions">{merchantKey !== null && <button className="icon-button" title="返回商家" aria-label="返回商家" onClick={() => onMerchant(null)}><ArrowLeft size={18} /></button>}<button className="icon-button" title="關閉明細" aria-label="關閉明細" onClick={onClose}><X size={18} /></button></div></div>
    {loading && <p role="status">載入中…</p>}{error && <p role="alert" className="category-error">{error}</p>}
    {!loading && !error && merchantKey === null && <ul className="category-merchant-list">{merchants.map(item => <li key={item.merchant_key}><button className="category-merchant-link" onClick={() => onMerchant(item.merchant_key)}><span>{item.display_name}<small>{item.transaction_count} 筆</small></span><strong>{formatMoney(item.net_amount, currency)}</strong><ChevronRight size={16} /></button><button className="icon-button" title={`分類 ${item.display_name}`} aria-label={`分類 ${item.display_name}`} onClick={() => setPicker({ id: item.transaction_id, description: item.display_name, category_id: category.category_id, currency, amount: item.net_amount, date: null, source_document_id: "" })}><Pencil size={16} /></button></li>)}{!merchants.length && <li>本期沒有此分類的支出</li>}</ul>}
    {!loading && !error && merchantKey !== null && <><p className="category-description">{merchantKey}</p><TransactionTable rows={result?.items ?? []} onOpenDocument={onOpenDocument} onCategory={setPicker} emptyTitle="本期沒有此商家的支出" /><div className="pagination"><span>{result?.total ?? 0} 筆</span><div><button className="small-action" disabled={page === 0} onClick={() => setPage(page - 1)}>上一頁</button><button className="small-action" disabled={(page + 1) * 50 >= (result?.total ?? 0)} onClick={() => setPage(page + 1)}>下一頁</button></div></div></>}
    {picker && <CategoryPicker transaction={picker} categories={categories} defaultScope={merchantKey === null ? "merchant" : "transaction"} onClose={() => setPicker(null)} onChanged={onChanged} />}
  </section>;
}
