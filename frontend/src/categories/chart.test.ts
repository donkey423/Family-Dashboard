import { describe, expect, test } from "vitest";
import { categoryColor, cents, decimal, donutSlices } from "./chart";
import type { CategoryTotal } from "../api";

const row = (id: number, amount = "1.00"): CategoryTotal => ({ category_id: String(id), code: String(id), name: String(id), net_amount: amount, transaction_count: 1 });
describe("category chart", () => {
  test.each([0, 1, 5, 6, 12])("%i categories aggregate without loss", count => {
    const rows = Array.from({ length: count }, (_, index) => row(index, String(count - index) + ".00"));
    const slices = donutSlices(rows);
    expect(slices.length).toBe(Math.min(count, 6));
    expect(slices.reduce((sum, slice) => sum + cents(slice.amount), 0n)).toBe(rows.reduce((sum, item) => sum + cents(item.net_amount), 0n));
    if (count) expect(slices.reduce((sum, slice) => sum + Math.round(Number(slice.percentage) * 100), 0)).toBe(10000);
    if (count > 5) expect(slices[5].name).toBe("其餘類別");
  });
  test("negative and zero values never enter the donut", () => {
    expect(donutSlices([row(0, "0.00"), row(1, "-5.00"), row(2, "5.00")]).map(item => item.id)).toEqual(["2"]);
  });
  test("uncategorized is not the other category", () => {
    const rows = Array.from({ length: 8 }, (_, index) => row(index));
    rows[0] = { ...row(0, "100.00"), code: "uncategorized", name: "未分類" };
    const slices = donutSlices(rows);
    expect(slices.map(item => item.name)).toContain("未分類");
    expect(slices.map(item => item.name)).toContain("其餘類別");
    expect(slices).toEqual(donutSlices([...rows].reverse()));
  });
  test("integer cents retain amounts above JS safe integer", () => {
    const amount = "9999999999999999.99";
    expect(decimal(cents(amount))).toBe(amount);
    expect(decimal(cents("-0.01"))).toBe("-0.01");
    expect(categoryColor("food")).toBe(categoryColor("food"));
  });
  test("generated Top-N groupings preserve every positive cent and stable percentages", () => {
    for (let count = 0; count <= 64; count++) {
      const rows = Array.from({ length: count }, (_, index) => row(index,
        decimal(BigInt(((count + 1) * (index + 7) * 423) % 30001 - 1000))));
      const slices = donutSlices(rows);
      const expected = rows.reduce((sum, item) => sum + (cents(item.net_amount) > 0n ? cents(item.net_amount) : 0n), 0n);
      expect(slices.reduce((sum, slice) => sum + cents(slice.amount), 0n)).toBe(expected);
      expect(slices).toEqual(donutSlices([...rows].reverse()));
      if (expected) expect(slices.reduce((sum, slice) => sum + Math.round(Number(slice.percentage) * 100), 0)).toBe(10000);
    }
  });
});
