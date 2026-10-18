// Pure helpers for formatting and date math, kept separate so they're easy to test.

import type { SpendingGroup, ToolCall } from './api'

// Used when a receipt didn't show a currency, and for totals of nothing (an empty account).
const DEFAULT_CURRENCY = 'USD'

export function formatMoney(amount: string | number | null, currency: string | null): string {
  if (amount === null) return '—'
  return Number(amount).toLocaleString('en-US', {
    style: 'currency',
    currency: currency ?? DEFAULT_CURRENCY,
  })
}

/** Short money for axis ticks: $1.2K instead of $1,200.00. */
export function formatMoneyCompact(value: number, currency: string | null): string {
  return value.toLocaleString('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
    style: 'currency',
    currency: currency ?? DEFAULT_CURRENCY,
  })
}

export function formatDate(isoDate: string | null): string {
  if (!isoDate) return '—'
  // Parse as a calendar date, not a UTC timestamp, so it never shifts a day.
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** "2026-09" -> "Sep", or "Jan '26" for January so the year change is visible. */
export function formatMonth(yearMonth: string): string {
  const [year, month] = yearMonth.split('-').map(Number)
  const name = new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short' })
  return month === 1 ? `${name} '${String(year).slice(2)}` : name
}

export function categoryLabel(category: string | null): string {
  if (!category) return 'Uncategorized'
  return category.charAt(0).toUpperCase() + category.slice(1)
}

function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export const PERIODS = {
  this_month: 'This month',
  last_month: 'Last month',
  last_90_days: 'Last 90 days',
  this_year: 'This year',
  all_time: 'All time',
} as const

export type Period = keyof typeof PERIODS

export function periodRange(period: Period, today: Date): { start_date?: string; end_date?: string } {
  const year = today.getFullYear()
  const month = today.getMonth()
  switch (period) {
    case 'this_month':
      return { start_date: isoDate(new Date(year, month, 1)), end_date: isoDate(today) }
    case 'last_month':
      return {
        start_date: isoDate(new Date(year, month - 1, 1)),
        end_date: isoDate(new Date(year, month, 0)), // day 0 = last day of previous month
      }
    case 'last_90_days':
      return {
        start_date: isoDate(new Date(year, month, today.getDate() - 89)),
        end_date: isoDate(today),
      }
    case 'this_year':
      return { start_date: isoDate(new Date(year, 0, 1)), end_date: isoDate(today) }
    case 'all_time':
      return {}
  }
}

/** The last `count` months as "YYYY-MM", oldest first, ending with the current month. */
export function recentMonths(today: Date, count: number): string[] {
  return Array.from({ length: count }, (_, i) =>
    isoDate(new Date(today.getFullYear(), today.getMonth() - (count - 1 - i), 1)).slice(0, 7),
  )
}

/**
 * The currency with the most spending. Charts show one currency at a time, because
 * amounts in different currencies can't be added or compared on one axis.
 */
export function primaryCurrency(groups: SpendingGroup[]): string | null {
  const totals = new Map<string | null, number>()
  for (const group of groups) {
    totals.set(group.currency, (totals.get(group.currency) ?? 0) + Number(group.total))
  }
  let best: string | null = null
  let bestTotal = -1
  for (const [currency, total] of totals) {
    if (total > bestTotal) {
      best = currency
      bestTotal = total
    }
  }
  return best
}

const TOOL_NAMES: Record<string, string> = {
  spending_summary: 'Spending summary',
  list_receipts: 'Receipt list',
  get_receipt: 'Receipt details',
  search_line_items: 'Item search',
}

/** The agent's tool call in words: "Spending summary · start date: 2026-09-01" */
export function describeToolCall(call: ToolCall): string {
  const details = Object.entries(call.arguments).map(([key, value]) => {
    const shown = Array.isArray(value) ? value.join(', ') : String(value)
    return `${key.replaceAll('_', ' ')}: ${shown}`
  })
  return [TOOL_NAMES[call.name] ?? call.name, ...details].join(' · ')
}
