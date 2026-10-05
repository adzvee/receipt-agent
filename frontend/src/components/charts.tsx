import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatMoney, formatMoneyCompact } from '../format'

// Chart styling follows one spec: a single accent color (validated for contrast in light
// and dark mode), bars at most 24px thick with 4px rounded ends, hairline gridlines,
// selective value labels, a hover tooltip on every bar, and a table view so no value is
// only reachable by hovering. Colors come from CSS variables in index.css.

export interface ChartRow {
  label: string
  value: number
  detail?: string // e.g. "3 receipts", shown in the tooltip
}

interface TooltipProps {
  active?: boolean
  payload?: { payload: ChartRow }[]
  currency: string | null
}

function ChartTooltip({ active, payload, currency }: TooltipProps) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return (
    <div className="chart-tooltip">
      <strong>{formatMoney(row.value, currency)}</strong>
      <span>{row.label}</span>
      {row.detail && <span className="muted">{row.detail}</span>}
    </div>
  )
}

const axisTick = { fill: 'var(--text-muted)', fontSize: 12 }

/** Horizontal bars, largest first. Every bar is labeled at its tip, so no value axis. */
export function CategoryChart({ rows, currency }: { rows: ChartRow[]; currency: string | null }) {
  const height = rows.length * 36 + 8
  return (
    <>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 84, bottom: 4, left: 0 }}>
          <XAxis type="number" hide domain={[0, 'dataMax']} />
          <YAxis
            type="category"
            dataKey="label"
            width={120}
            tickLine={false}
            axisLine={{ stroke: 'var(--baseline)' }}
            tick={{ fill: 'var(--text-secondary)', fontSize: 13 }}
          />
          <Tooltip cursor={{ fill: 'var(--hover-wash)' }} content={<ChartTooltip currency={currency} />} />
          <Bar
            dataKey="value"
            fill="var(--series-1)"
            radius={[0, 4, 4, 0]}
            maxBarSize={24}
            activeBar={{ fillOpacity: 0.8 }}
            isAnimationActive={false}
          >
            <LabelList
              dataKey="value"
              position="right"
              formatter={(value) => formatMoney(Number(value), currency)}
              style={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <TableView rows={rows} currency={currency} labelHeading="Category" />
    </>
  )
}

/**
 * Monthly columns, read with the y-axis and tooltip. The current month's total is shown in
 * the card's subtitle instead of on the column, where it would be clipped on narrow screens.
 */
export function MonthlyChart({ rows, currency }: { rows: ChartRow[]; currency: string | null }) {
  return (
    <>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: 'var(--baseline)' }}
            tick={axisTick}
          />
          <YAxis
            width={56}
            tickLine={false}
            axisLine={false}
            tick={axisTick}
            tickFormatter={(value: number) => formatMoneyCompact(value, currency)}
          />
          <Tooltip cursor={{ fill: 'var(--hover-wash)' }} content={<ChartTooltip currency={currency} />} />
          <Bar
            dataKey="value"
            fill="var(--series-1)"
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            activeBar={{ fillOpacity: 0.8 }}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
      <TableView rows={rows} currency={currency} labelHeading="Month" />
    </>
  )
}

function TableView({
  rows,
  currency,
  labelHeading,
}: {
  rows: ChartRow[]
  currency: string | null
  labelHeading: string
}) {
  return (
    <details className="table-view">
      <summary>Show as table</summary>
      <table>
        <thead>
          <tr>
            <th>{labelHeading}</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td className="num">{formatMoney(row.value, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
