import type { Transaction } from "./api";
import { EmptyState } from "./EmptyState";

type TransactionTableProps = {
  rows: Transaction[];
  onOpenDocument?: (documentId: string) => void;
  emptyTitle?: string;
  emptyDetail?: string;
};

const money = (value: string, currency: string) => {
  try { return new Intl.NumberFormat("zh-TW", { style: "currency", currency }).format(Number(value)); }
  catch { return `${currency} ${value}`; }
};

export function TransactionTable({ rows, onOpenDocument, emptyTitle = "尚無交易資料", emptyDetail = "匯入通用 CSV 後，交易會顯示在這裡。" }: TransactionTableProps) {
  if (!rows.length) return <EmptyState title={emptyTitle} detail={emptyDetail} />;
  return <div className="table-wrap"><table><thead><tr><th>日期</th><th>項目</th><th>金額</th>{onOpenDocument && <th>來源</th>}</tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td className="date-cell">{row.date ?? "未提供"}</td><td><span className="transaction-name">{row.description}</span></td><td className={Number(row.amount) < 0 ? "amount expense" : "amount income"}>{money(row.amount, row.currency)}</td>{onOpenDocument && <td className="source-cell"><button className="text-button source-link" aria-label={`查看 ${row.description} 的來源文件`} onClick={() => onOpenDocument(row.source_document_id)}>文件</button></td>}</tr>)}</tbody></table></div>;
}
