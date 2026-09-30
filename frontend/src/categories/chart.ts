import type { CategoryTotal } from "../api";

export const cents = (value: string): bigint => {
  const negative = value.startsWith("-");
  const [integer, fraction = ""] = value.replace(/^-/, "").split(".");
  const amount = BigInt(integer) * 100n + BigInt(fraction.padEnd(2, "0").slice(0, 2));
  return negative ? -amount : amount;
};
export const decimal = (value: bigint) => `${value < 0n ? "-" : ""}${(value < 0n ? -value : value) / 100n}.${String((value < 0n ? -value : value) % 100n).padStart(2, "0")}`;
export const formatMoney = (value: string, currency: string) => {
  try { return new Intl.NumberFormat("zh-TW", { style: "currency", currency }).format(Number(value)); }
  catch { return `${currency} ${value}`; }
};
const colors: Record<string, string> = { food: "#16866b", groceries: "#92ad30", transport: "#3572b0", shopping: "#cc5a72", home: "#af7934", family: "#8659a6", health: "#4a9a94", entertainment: "#ca734c", travel: "#4985bc", education: "#637b47", finance: "#b24b51", uncategorized: "#66717a", income: "#387f54", transfer: "#888", other: "#abb3bb" };
export const categoryColor = (code: string) => colors[code] ?? ["#16866b", "#cc5a72", "#3572b0", "#af7934"][Array.from(code).reduce((total, character) => total + character.charCodeAt(0), 0) % 4];
export type ChartSlice = { id: string; code: string; name: string; amount: string; value: number; percentage: string; categories: CategoryTotal[] };

export function donutSlices(categories: CategoryTotal[]): ChartSlice[] {
  const positive = categories.filter(item => cents(item.net_amount) > 0n).sort((a, b) => {
    const difference = cents(b.net_amount) - cents(a.net_amount);
    return difference > 0n ? 1 : difference < 0n ? -1 : a.code.localeCompare(b.code);
  });
  const groups = positive.length <= 5 ? positive.map(item => [item]) : [...positive.slice(0, 5).map(item => [item]), positive.slice(5)];
  const amounts = groups.map(group => group.reduce((total, item) => total + cents(item.net_amount), 0n));
  const total = amounts.reduce((sum, amount) => sum + amount, 0n);
  if (!total) return [];
  const basis = amounts.map(amount => amount * 10000n / total);
  let remainder = Number(10000n - basis.reduce((sum, amount) => sum + amount, 0n));
  const ranks = amounts.map((amount, index) => ({ index, remainder: amount * 10000n % total })).sort((a, b) => a.remainder > b.remainder ? -1 : a.remainder < b.remainder ? 1 : a.index - b.index);
  for (const rank of ranks) { if (remainder-- > 0) basis[rank.index] += 1n; }
  return groups.map((group, index) => ({ id: positive.length > 5 && index === 5 ? "__other__" : group[0].category_id, code: positive.length > 5 && index === 5 ? "other" : group[0].code,
    name: positive.length > 5 && index === 5 ? "其餘類別" : group[0].name, amount: decimal(amounts[index]), value: Number(amounts[index]), percentage: (Number(basis[index]) / 100).toFixed(2), categories: group }));
}
