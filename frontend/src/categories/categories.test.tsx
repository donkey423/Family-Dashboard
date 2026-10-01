import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { api, type Category, type CategoryBatchImpact, type CategorySpending, type CategoryTotal, type Transaction } from "../api";
import { CategoryDonut } from "./CategoryDonut";
import { CategoryPicker } from "./CategoryPicker";
import { CategoryBatchPicker } from "./CategoryBatchPicker";
import { CategoryDetailPanel } from "./CategoryDetailPanel";
import { SpendingByCategory } from "./SpendingByCategory";
import { UncategorizedReview } from "./UncategorizedReview";
import { CategorySettings } from "./CategorySettings";
import { TransactionTable } from "../TransactionTable";

vi.mock("recharts", () => ({ ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, Pie: ({ data, onClick }: { data: { id: string }[]; onClick: (entry: { id: string }) => void }) => <div>{data.map(entry => <button key={entry.id} data-testid={`slice-${entry.id}`} onClick={() => onClick(entry)} />)}</div>, Cell: () => null }));
const categories: Category[] = ["food", "travel", "uncategorized"].map((code, sort_order) => ({ id: code, code, display_name: code === "food" ? "餐飲" : code === "travel" ? "旅遊" : "未分類", is_active: true, is_system: true, sort_order }));
const total: CategoryTotal = { category_id: "food", code: "food", name: "餐飲", net_amount: "100.00", transaction_count: 1 };
const tx: Transaction = { id: "t", source_document_id: "d", date: "2026-09-01", description: "Coffee shop", amount: "-100.00", currency: "TWD", category_id: "food", category_name: "餐飲", category_source: "override" };
const summary: CategorySpending = { month: "2026-09", currency: "TWD", dashboard_expense: "100.00", positive_category_total: "100.00", refund_credit_total: "0.00", categories: [total], negative_categories: [] };
const batchImpact: CategoryBatchImpact = { impact_token: "b".repeat(64), changed_count: 1, affected_count: 1, protected_override_count: 0, months: ["2026-09"], changed_transaction_ids: ["t"], items: [{ ...tx, category_source: "uncategorized", protected_override: false }] };
beforeEach(() => {
  vi.spyOn(api, "categories").mockResolvedValue(categories);
  vi.spyOn(api, "categoryRules").mockResolvedValue([]);
  vi.spyOn(api, "spendingByCategory").mockResolvedValue(summary);
  vi.spyOn(api, "categoryMerchants").mockResolvedValue({ items: [{ merchant_key: "COFFEE SHOP", display_name: "Coffee shop", transaction_id: "t", net_amount: "100.00", transaction_count: 1 }] });
  vi.spyOn(api, "uncategorizedMerchants").mockResolvedValue({ items: [] });
  vi.spyOn(api, "transactions").mockResolvedValue({ items: [tx], total: 1, limit: 50, offset: 0 });
  vi.spyOn(api, "assignCategory").mockResolvedValue(tx);
  vi.spyOn(api, "categoryImpact").mockResolvedValue({ impact_token: "a".repeat(64), merchant_key: "COFFEE SHOP", changed_count: 2, affected_count: 2, protected_override_count: 1, months: ["2026-08", "2026-09"], samples: [] });
  vi.spyOn(api, "clearCategoryOverride").mockResolvedValue(tx);
  vi.spyOn(api, "categoryBatchImpact").mockResolvedValue(batchImpact);
  vi.spyOn(api, "assignCategoryBatch").mockResolvedValue({ changed_count: 1, protected_override_count: 0 });
});

test("batch requires explicit target and preview before saving only selected rows", async () => {
  const changed = vi.fn(), close = vi.fn();
  render(<CategoryBatchPicker transactions={[tx]} categories={categories} onChanged={changed} onClose={close} />);
  expect(screen.getByRole("button", { name: "確認批次分類" })).toHaveProperty("disabled", true);
  expect(api.categoryBatchImpact).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog").textContent).toContain("2026-09-01");
  fireEvent.change(screen.getByLabelText("批次分類目標"), { target: { value: "travel" } });
  await screen.findByText("將修改 1 筆；保留 0 筆單筆指定。");
  expect(api.categoryBatchImpact).toHaveBeenCalledWith(["t"], "travel");
  fireEvent.click(screen.getByRole("button", { name: "確認批次分類" }));
  await waitFor(() => expect(api.assignCategoryBatch).toHaveBeenCalledWith(["t"], "travel", "b".repeat(64)));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
  expect(changed).toHaveBeenCalledTimes(1);
  expect(api.assignCategory).not.toHaveBeenCalled();
});

test("batch preview failure and stale write block retries until preview refreshes", async () => {
  vi.mocked(api.categoryBatchImpact).mockRejectedValueOnce(new Error("批次預覽失敗"));
  const close = vi.fn();
  render(<CategoryBatchPicker transactions={[tx]} categories={categories} onChanged={vi.fn()} onClose={close} />);
  fireEvent.change(screen.getByLabelText("批次分類目標"), { target: { value: "travel" } });
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "批次預覽失敗");
  expect(screen.getByRole("button", { name: "確認批次分類" })).toHaveProperty("disabled", true);
  expect(api.assignCategoryBatch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重新預覽影響" }));
  await screen.findByText("將修改 1 筆；保留 0 筆單筆指定。");
  vi.mocked(api.assignCategoryBatch).mockRejectedValueOnce(new Error("資料已變動"));
  fireEvent.click(screen.getByRole("button", { name: "確認批次分類" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "資料已變動");
  expect(screen.getByRole("button", { name: "確認批次分類" })).toHaveProperty("disabled", true);
  expect(close).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重新預覽影響" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "確認批次分類" })).toHaveProperty("disabled", false));
});

test("batch ignores stale preview after target changes", async () => {
  let resolve!: (value: CategoryBatchImpact) => void;
  vi.mocked(api.categoryBatchImpact).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  render(<CategoryBatchPicker transactions={[tx]} categories={categories} onChanged={vi.fn()} onClose={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("批次分類目標"), { target: { value: "food" } });
  fireEvent.change(screen.getByLabelText("批次分類目標"), { target: { value: "travel" } });
  await screen.findByText("將修改 1 筆；保留 0 筆單筆指定。");
  await act(async () => resolve({ ...batchImpact, changed_count: 9, impact_token: "c".repeat(64) }));
  expect(screen.queryByText("將修改 9 筆；保留 0 筆單筆指定。")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "確認批次分類" }));
  await waitFor(() => expect(api.assignCategoryBatch).toHaveBeenCalledWith(["t"], "travel", "b".repeat(64)));
});

test("batch protects manual rows and selection resets when month changes", async () => {
  const unknown = { ...tx, id: "unknown", description: "Unsorted", category_source: "uncategorized" };
  vi.mocked(api.transactions).mockResolvedValue({ items: [tx, unknown], total: 2, limit: 50, offset: 0 });
  const props = { category: total, currency: "TWD", categories, version: 0, merchantKey: "SHOP", onMerchant: vi.fn(), onClose: vi.fn(), onChanged: vi.fn() };
  const { rerender } = render(<CategoryDetailPanel {...props} month="2026-09" />);
  const checks = await screen.findAllByRole("checkbox");
  expect(checks[0]).toHaveProperty("disabled", true);
  fireEvent.click(checks[1]);
  fireEvent.click(screen.getByRole("button", { name: "批次分類 (1)" }));
  expect(screen.getByRole("dialog").textContent).toContain("Unsorted");
  expect(screen.getByRole("dialog").textContent).not.toContain("Coffee shop");
  rerender(<CategoryDetailPanel {...props} month="2026-08" />);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(await screen.findByRole("button", { name: "批次分類" })).toHaveProperty("disabled", true);
});

test("batch pending write cannot be dismissed with Escape", async () => {
  let resolve!: (value: { changed_count: number; protected_override_count: number }) => void;
  vi.mocked(api.assignCategoryBatch).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const close = vi.fn();
  render(<CategoryBatchPicker transactions={[tx]} categories={categories} onChanged={vi.fn()} onClose={close} />);
  fireEvent.change(screen.getByLabelText("批次分類目標"), { target: { value: "travel" } });
  await screen.findByText("將修改 1 筆；保留 0 筆單筆指定。");
  fireEvent.click(screen.getByRole("button", { name: "確認批次分類" }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
  await act(async () => resolve({ changed_count: 1, protected_override_count: 0 }));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
});

test.each([true, false])("long transaction/category labels retain semantic mobile grid cells (source=%s)", withSource => {
  const longTx = { ...tx, description: "LONGMERCHANT".repeat(30), category_name: "超長分類名稱".repeat(15) };
  const { container } = render(<TransactionTable rows={[longTx]} onCategory={vi.fn()} onOpenDocument={withSource ? vi.fn() : undefined} />);
  expect(container.querySelector("table")?.classList.contains("with-category")).toBe(true);
  expect(container.querySelector(".category-cell")?.textContent).toBe(longTx.category_name);
  expect(container.querySelector(".source-cell") !== null).toBe(withSource);
  expect(container.querySelector(".transaction-name")?.textContent).toBe(longTx.description);
});

test("donut has keyboard-accessible matching labels", async () => {
  const selected = vi.fn(); render(<CategoryDonut categories={[total]} currency="TWD" onSelect={selected} />);
  const user = userEvent.setup(); await user.tab(); await user.keyboard("{Enter}");
  expect(selected.mock.calls[0][0].id).toBe("food");
  expect(screen.getByRole("button", { name: /餐飲.*100.*100.00%/ })).toBeTruthy();
});

test("slice, Enter and Space select the same category", async () => {
  const selected = vi.fn(); render(<CategoryDonut categories={[total]} currency="TWD" onSelect={selected} />);
  fireEvent.click(screen.getByTestId("slice-food"));
  const user = userEvent.setup(); screen.getByRole("button", { name: /餐飲.*100.00%/ }).focus();
  await user.keyboard("{Enter} ");
  expect(selected).toHaveBeenCalledTimes(3);
  expect(selected.mock.calls.map(([slice]) => slice.id)).toEqual(["food", "food", "food"]);
});
test("empty donut stays useful without a pie", () => {
  render(<CategoryDonut categories={[]} currency="TWD" onSelect={vi.fn()} />);
  expect(screen.getByText("本期沒有正淨支出")).toBeTruthy();
});
test.each(["transaction", "merchant"] as const)("picker saves %s scope and refreshes", async scope => {
  const changed = vi.fn(), close = vi.fn(); render(<CategoryPicker transaction={tx} categories={categories} onChanged={changed} onClose={close} defaultScope={scope} />);
  fireEvent.change(screen.getByLabelText("分類"), { target: { value: "travel" } });
  if (scope === "merchant") await waitFor(() => expect(screen.getByRole("button", { name: "儲存" })).toHaveProperty("disabled", false));
  fireEvent.click(screen.getByRole("button", { name: "儲存" }));
  await waitFor(() => expect(api.assignCategory).toHaveBeenCalledWith(...(scope === "merchant" ? ["t", "travel", scope, "a".repeat(64)] : ["t", "travel", scope])));
  await waitFor(() => expect(close).toHaveBeenCalled()); expect(changed).toHaveBeenCalled();
});
test("failed PATCH retains category and dialog; clear override uses DELETE", async () => {
  vi.mocked(api.assignCategory).mockRejectedValue(new Error("衝突"));
  const close = vi.fn(); render(<CategoryPicker transaction={tx} categories={categories} onChanged={vi.fn()} onClose={close} />);
  fireEvent.click(screen.getByRole("button", { name: "儲存" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "衝突"); expect(close).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "恢復規則分類" }));
  await waitFor(() => expect(api.clearCategoryOverride).toHaveBeenCalledWith("t"));
});
test("category to merchant to transaction drilldown preserves month/currency and URL", async () => {
  render(<SpendingByCategory month="2026-09" currency="TWD" currencies={["TWD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: /餐飲.*100.00%/ }));
  expect(new URLSearchParams(window.location.search).get("category")).toBe("food");
  fireEvent.click(await screen.findByRole("button", { name: /Coffee shop.*100/ }));
  await waitFor(() => expect(api.transactions).toHaveBeenCalledWith(expect.objectContaining({ month: "2026-09", currency: "TWD", category_id: "food", merchant_key: "COFFEE SHOP", consumption_only: true })));
  expect(await screen.findByRole("button", { name: "修改 Coffee shop 的分類" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "返回商家" }));
  await screen.findByRole("button", { name: /Coffee shop.*100/ });
});
test("other categories open an explicit category list; negative refund is clickable", async () => {
  const list = Array.from({ length: 7 }, (_, index) => ({ ...total, category_id: `cat${index}`, code: `cat${index}`, name: `分類${index}`, net_amount: String(100 - index) + ".00" }));
  const refund = { ...total, category_id: "travel", name: "退款旅遊", net_amount: "-5.00" };
  vi.mocked(api.spendingByCategory).mockResolvedValue({ ...summary, categories: [...list, refund], negative_categories: [refund] });
  render(<SpendingByCategory month="2026-09" currency="TWD" currencies={["TWD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: /其餘類別.*%/ }));
  expect(screen.getByRole("button", { name: /分類6/ })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /退款旅遊/ }));
  await waitFor(() => expect(api.categoryMerchants).toHaveBeenCalledWith("2026-09", "TWD", "travel"));
});
test("stale response cannot replace newer month data", async () => {
  let resolve!: (value: CategorySpending) => void;
  vi.mocked(api.spendingByCategory).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const { rerender } = render(<SpendingByCategory month="2026-08" currency="TWD" currencies={["TWD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  rerender(<SpendingByCategory month="2026-09" currency="TWD" currencies={["TWD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  await screen.findByRole("button", { name: /餐飲.*100.00%/ });
  await act(async () => resolve({ ...summary, categories: [{ ...total, name: "過時資料" }] }));
  expect(screen.queryByText("過時資料")).toBeNull();
});

test("stale currency response cannot replace the selected currency", async () => {
  let resolve!: (value: CategorySpending) => void;
  vi.mocked(api.spendingByCategory).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  render(<SpendingByCategory month="2026-09" currency="" currencies={["TWD", "USD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("分類支出幣別"), { target: { value: "USD" } });
  await waitFor(() => expect(api.spendingByCategory).toHaveBeenLastCalledWith("2026-09", "USD"));
  await screen.findByRole("button", { name: /餐飲.*100.00%/ });
  await act(async () => resolve({ ...summary, categories: [{ ...total, name: "過時幣別" }] }));
  expect(screen.queryByText("過時幣別")).toBeNull();
});

test("URL drilldown survives remount and close clears the local currency filter", async () => {
  window.history.replaceState({}, "", "/?month=2026-09&currency=TWD&category=food&merchant=COFFEE+SHOP");
  render(<SpendingByCategory month="2026-09" currency="" currencies={["TWD", "USD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  await screen.findByRole("button", { name: "修改 Coffee shop 的分類" });
  expect(api.transactions).toHaveBeenCalledWith(expect.objectContaining({ category_id: "food", merchant_key: "COFFEE SHOP", month: "2026-09", currency: "TWD" }));
  fireEvent.click(screen.getByRole("button", { name: "關閉明細" }));
  expect(new URLSearchParams(window.location.search).has("category")).toBe(false);
  expect(new URLSearchParams(window.location.search).has("merchant")).toBe(false);
  expect(new URLSearchParams(window.location.search).has("currency")).toBe(false);
});

test("currency with no spending has an explicit empty state", async () => {
  vi.mocked(api.spendingByCategory).mockResolvedValue({ ...summary, currency: "JPY", dashboard_expense: "0.00", positive_category_total: "0.00", categories: [] });
  render(<SpendingByCategory month="2026-09" currency="JPY" currencies={["TWD", "JPY"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  expect(await screen.findByText("本期沒有正淨支出")).toBeTruthy();
  expect(screen.queryByTestId("slice-food")).toBeNull();
});

test("merchant transaction pagination and source document actions preserve filters", async () => {
  vi.mocked(api.transactions).mockResolvedValue({ items: [tx], total: 51, limit: 50, offset: 0 });
  const open = vi.fn();
  render(<CategoryDetailPanel category={total} month="2026-09" currency="TWD" categories={categories} version={0} merchantKey="COFFEE SHOP" onMerchant={vi.fn()} onClose={vi.fn()} onChanged={vi.fn()} onOpenDocument={open} />);
  fireEvent.click(await screen.findByRole("button", { name: "下一頁" }));
  await waitFor(() => expect(api.transactions).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50, limit: 50, category_id: "food", consumption_only: true })));
  const source = await screen.findByRole("button", { name: "查看 Coffee shop 的來源文件" });
  fireEvent.click(source);
  expect(open).toHaveBeenCalledWith("d");
});
test("uncategorized review opens actual transactions and defaults to one transaction", async () => {
  vi.mocked(api.uncategorizedMerchants).mockResolvedValue({ items: [{ merchant_key: "SHOP", display_name: "Shop", transaction_id: "t", net_amount: "10.00", transaction_count: 2 }] });
  render(<UncategorizedReview month="2026-09" currency="TWD" categories={categories} version={0} onChanged={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "分類 Shop" }));
  fireEvent.click(await screen.findByRole("button", { name: "修改 Coffee shop 的分類" }));
  expect((screen.getByRole("radio", { name: "僅此筆交易" }) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByRole("dialog").textContent).toContain("2026-09-01");
  expect(api.transactions).toHaveBeenCalledWith(expect.objectContaining({ category_id: "uncategorized", merchant_key: "SHOP", month: "2026-09", currency: "TWD", consumption_only: true }));
});

test("merchant preview failure blocks writes and stale save requires a new preview", async () => {
  vi.mocked(api.categoryImpact).mockRejectedValueOnce(new Error("預覽失敗"));
  render(<CategoryPicker transaction={tx} categories={categories} onChanged={vi.fn()} onClose={vi.fn()} />);
  fireEvent.click(screen.getByRole("radio", { name: "此商家的現在與未來交易" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "預覽失敗");
  expect(screen.getByRole("button", { name: "儲存" })).toHaveProperty("disabled", true);
  expect(api.assignCategory).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重新預覽影響" }));
  await screen.findByText("將改變 2 筆既有交易；保留 1 筆單筆指定。");
  vi.mocked(api.assignCategory).mockRejectedValueOnce(new Error("資料已變動"));
  fireEvent.click(screen.getByRole("button", { name: "儲存" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "資料已變動");
  expect(screen.getByRole("button", { name: "儲存" })).toHaveProperty("disabled", true);
});

test("unknown donut opens review rather than another category", async () => {
  vi.mocked(api.spendingByCategory).mockResolvedValue({ ...summary, categories: [{ ...total, category_id: "uncategorized", code: "uncategorized", name: "未分類" }] });
  render(<SpendingByCategory month="2026-09" currency="TWD" currencies={["TWD"]} version={0} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: /未分類.*100\.00%/ }));
  await waitFor(() => expect(api.uncategorizedMerchants).toHaveBeenCalledWith("2026-09", "TWD"));
  expect(window.location.search).not.toContain("category=");
});
test("detail loads only correct merchant page and reports load error", async () => {
  vi.mocked(api.transactions).mockRejectedValue(new Error("無法讀取"));
  render(<CategoryDetailPanel category={total} month="2026-09" currency="USD" categories={categories} version={0} merchantKey="SHOP" onMerchant={vi.fn()} onClose={vi.fn()} onChanged={vi.fn()} onOpenDocument={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "無法讀取");
  expect(api.transactions).toHaveBeenCalledWith(expect.objectContaining({ currency: "USD", merchant_key: "SHOP" }));
});
test("category settings protects system fallback and reports duplicate without optimistic mutation", async () => {
  vi.spyOn(api, "createCategory").mockRejectedValue(new Error("已存在"));
  render(<CategorySettings />);
  expect(await screen.findByLabelText("啟用 未分類")).toHaveProperty("disabled", true);
  fireEvent.change(screen.getByLabelText("新分類名稱"), { target: { value: "New" } });
  fireEvent.change(screen.getByLabelText("新分類代碼"), { target: { value: "new" } });
  fireEvent.click(screen.getByRole("button", { name: "新增分類" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("已存在"));
  expect(screen.queryByText("new", { exact: true })).toBeNull();
});

test("picker cannot dismiss a pending write with Escape", async () => {
  let resolve!: (value: Transaction) => void;
  vi.mocked(api.assignCategory).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const close = vi.fn(); render(<CategoryPicker transaction={tx} categories={categories} onChanged={vi.fn()} onClose={close} />);
  fireEvent.click(screen.getByRole("button", { name: "儲存" }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
  await act(async () => resolve(tx));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
});

test("rule text and priority are editable without changing match type", async () => {
  vi.mocked(api.categoryRules).mockResolvedValue([{ id: "r", category_id: "food", pattern: "COFFEE", match_type: "contains", priority: 0, enabled: true }]);
  vi.spyOn(api, "updateCategoryRule").mockResolvedValue({ id: "r", category_id: "food", pattern: "CAFE", match_type: "contains", priority: 5, enabled: true });
  render(<CategorySettings />);
  fireEvent.click(await screen.findByRole("button", { name: "修改規則 COFFEE" }));
  fireEvent.change(screen.getByLabelText("修改商家規則文字"), { target: { value: "CAFE" } });
  fireEvent.change(screen.getByLabelText("修改規則優先順序"), { target: { value: "5" } });
  fireEvent.click(screen.getByRole("button", { name: "儲存規則" }));
  await waitFor(() => expect(api.updateCategoryRule).toHaveBeenCalledWith("r", { pattern: "CAFE", priority: 5 }));
});
