import type { Transaction } from "./api";
import { EmptyState } from "./EmptyState";

type TransactionTableProps = {
  rows: Transaction[];
  onOpenDocument?: (documentId: string) => void;
  emptyTitle?: string;
  emptyDetail?: string;
  onCategory?: (row: Transaction) => void;
  selection?: { ids: string[]; onToggle: (id: string) => void };
};

const money = (value: string, currency: string) => {
  try { return new Intl.NumberFormat("zh-TW", { style: "currency", currency }).format(Number(value)); }
  catch { return `${currency} ${value}`; }
};

export function TransactionTable({ rows, onOpenDocument, onCategory, selection, emptyTitle = "尚無交易資料", emptyDetail = "匯入通用 CSV 後，交易會顯示在這裡。" }: TransactionTableProps) {
  if (!rows.length) return <EmptyState title={emptyTitle} detail={emptyDetail} />;
  const showCategory = rows.some(row => row.category_name) || !!onCategory;
  return <div className="table-wrap"><table className={showCategory ? "transaction-table with-category" : "transaction-table"}><thead><tr><th>日期</th><th>項目</th><th>金額</th>{showCategory && <th>分類</th>}{onOpenDocument && <th>來源</th>}</tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td className="date-cell">{row.date ?? "未提供"}</td><td>{selection ? <label className="transaction-selection"><input type="checkbox" checked={selection.ids.includes(row.id)} disabled={row.category_source === "override"} onChange={() => selection.onToggle(row.id)} aria-label={`選取 ${row.description} ${row.date ?? "未提供日期"} ${money(row.amount, row.currency)}`} /><span className="transaction-name">{row.description}</span></label> : <span className="transaction-name">{row.description}</span>}</td><td className={Number(row.amount) < 0 ? "amount expense" : "amount income"}>{money(row.amount, row.currency)}</td>{showCategory && <td className="category-cell">{onCategory ? <button className="text-button category-table-button" onClick={() => onCategory(row)} aria-label={`修改 ${row.description} 的分類`}>{row.category_name ?? "未分類"}</button> : row.category_name ?? "未分類"}</td>}{onOpenDocument && <td className="source-cell"><button className="text-button source-link" aria-label={`查看 ${row.description} 的來源文件`} onClick={() => onOpenDocument(row.source_document_id)}>文件</button></td>}</tr>)}</tbody></table></div>;
}
