import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import type { CategoryTotal } from "../api";
import { categoryColor, donutSlices, formatMoney, type ChartSlice } from "./chart";

export function CategoryDonut({ categories, currency, onSelect }: { categories: CategoryTotal[]; currency: string; onSelect: (slice: ChartSlice) => void }) {
  const slices = donutSlices(categories);
  if (!slices.length) return <p className="category-empty">本期沒有正淨支出</p>;
  return <div className="category-chart-layout">
    <div className="category-chart" aria-hidden="true"><ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 300, height: 272 }}><PieChart><Pie data={slices} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="90%" paddingAngle={2} isAnimationActive={false} onClick={(entry) => { const slice = slices.find(item => item.id === entry.id); if (slice) onSelect(slice); }}>{slices.map(item => <Cell key={item.id} fill={categoryColor(item.code)} stroke="none" />)}</Pie></PieChart></ResponsiveContainer></div>
    <ul className="category-legend">{slices.map(slice => <li key={slice.id}><button onClick={() => onSelect(slice)} aria-label={`${slice.name} ${formatMoney(slice.amount, currency)} ${slice.percentage}%`}><span className="category-swatch" style={{ background: categoryColor(slice.code) }} /><span className="category-label">{slice.name}<small>{slice.percentage}%</small></span><strong>{formatMoney(slice.amount, currency)}</strong></button></li>)}</ul>
  </div>;
}
