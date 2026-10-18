import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Rectangle,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
  type YAxisTickContentProps,
} from 'recharts'
import { formatMoney, formatMoneyCompact } from '../format'
import { categoryColor } from '../categories'
import { CategoryIcon, CategoryTag } from './CategoryIcon'

// Chart styling follows one spec: bars at most 24px thick with 4px rounded ends, hairline
// gridlines, selective value labels, a hover tooltip on every bar, and a table view so no
// value is only reachable by hovering. The monthly chart uses the single accent color;
// category bars use each category's own color and icon (see categories.tsx). Colors come
// from CSS variables in index.css, validated for contrast in light and dark mode.

export interface ChartRow {
  label: string
  value: number
  detail?: string // e.g. "3 receipts", shown in the tooltip
  category?: string | null // set on category rows, for their color and icon
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

const CATEGORY_AXIS_WIDTH = 140

/** Category axis label: the category's icon, then its name, left-aligned. */
function CategoryTick({ x, y, payload, rows }: YAxisTickContentProps & { rows: ChartRow[] }) {
  const category = rows[payload.index]?.category ?? null
  const left = Number(x) - CATEGORY_AXIS_WIDTH + 4
  const middle = Number(y)
  return (
    <g>
      <CategoryIcon category={category} x={left} y={middle - 8} size={16} />
      <text x={left + 24} y={middle} dy="0.35em" fill="var(--text-secondary)" fontSize={13}>
        {String(payload.value)}
      </text>
    </g>
  )
}

/** Horizontal bars, largest first. Every bar is labeled at its tip, so no value axis. */
export function CategoryChart({ rows, currency }: { rows: ChartRow[]; currency: string | null }) {
  const height = rows.length * 36 + 8
  const renderBar = ({ isActive, ...props }: BarShapeProps) => (
    <Rectangle
      {...props}
      fill={categoryColor(rows[props.index]?.category ?? null)}
      fillOpacity={isActive ? 0.8 : 1}
    />
  )
  return (
    <>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 84, bottom: 4, left: 0 }}>
          <XAxis type="number" hide domain={[0, 'dataMax']} />
          <YAxis
            type="category"
            dataKey="label"
            width={CATEGORY_AXIS_WIDTH}
            tickLine={false}
            axisLine={{ stroke: 'var(--baseline)' }}
            tick={(props: YAxisTickContentProps) => <CategoryTick {...props} rows={rows} />}
          />
          <Tooltip cursor={{ fill: 'var(--hover-wash)' }} content={<ChartTooltip currency={currency} />} />
          <Bar
            dataKey="value"
            radius={[0, 4, 4, 0]}
            maxBarSize={24}
            shape={renderBar}
            activeBar={renderBar}
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
              <td>{row.category !== undefined ? <CategoryTag category={row.category} /> : row.label}</td>
              <td className="num">{formatMoney(row.value, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
