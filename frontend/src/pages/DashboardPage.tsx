import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getSpending, listReceipts, type SpendingGroup } from '../api'
import { ChatPanel } from '../components/ChatPanel'
import { CategoryChart, MonthlyChart, type ChartRow } from '../components/charts'
import { OpenFlagBadges } from '../components/FlagBadge'
import {
  categoryLabel,
  formatDate,
  formatMoney,
  formatMonth,
  PERIODS,
  periodRange,
  primaryCurrency,
  recentMonths,
  type Period,
} from '../format'

const MONTHS_SHOWN = 12

function inCurrency(groups: SpendingGroup[], currency: string | null): SpendingGroup[] {
  return groups.filter((group) => group.currency === currency)
}

/** e.g. "Also €20.00 in EUR (not included above)." when receipts use several currencies. */
function OtherCurrencies({ groups, shown }: { groups: SpendingGroup[]; shown: string | null }) {
  const totals = new Map<string, number>()
  for (const group of groups) {
    if (group.currency !== shown && group.currency) {
      totals.set(group.currency, (totals.get(group.currency) ?? 0) + Number(group.total))
    }
  }
  if (!totals.size) return null
  const parts = [...totals].map(([currency, total]) => formatMoney(total, currency))
  return <p className="muted">Also {parts.join(', ')} in other currencies (not included above).</p>
}

export function DashboardPage() {
  const [period, setPeriod] = useState<Period>('this_month')
  const [today] = useState(() => new Date()) // fixed for the page's lifetime
  const months = recentMonths(today, MONTHS_SHOWN)
  const range = periodRange(period, today)

  const trend = useQuery({
    queryKey: ['spending', 'month', months[0]],
    queryFn: () => getSpending({ group_by: 'month', start_date: `${months[0]}-01` }),
  })
  const byCategory = useQuery({
    queryKey: ['spending', 'category', range],
    queryFn: () => getSpending({ group_by: 'category', ...range }),
    placeholderData: keepPreviousData, // keep the old chart (dimmed) while the new one loads
  })
  const flagged = useQuery({
    queryKey: ['receipts', { needsReview: true }],
    queryFn: () => listReceipts({ needsReview: true }),
  })

  const trendGroups = trend.data?.groups ?? []
  const trendCurrency = primaryCurrency(trendGroups)
  const monthTotals = new Map(inCurrency(trendGroups, trendCurrency).map((g) => [g.month, g]))
  const monthRows: ChartRow[] = months.map((month) => {
    const group = monthTotals.get(month)
    return {
      label: formatMonth(month),
      value: Number(group?.total ?? 0),
      detail: `${group?.receipt_count ?? 0} receipts`,
    }
  })

  const categoryGroups = byCategory.data?.groups ?? []
  const currency = primaryCurrency(categoryGroups)
  const shownGroups = inCurrency(categoryGroups, currency)
  const categoryRows: ChartRow[] = shownGroups.map((group) => ({
    label: categoryLabel(group.category === '(none)' ? null : (group.category ?? null)),
    value: Number(group.total),
    detail: `${group.receipt_count} receipts`,
  }))
  const periodTotal = shownGroups.reduce((sum, group) => sum + Number(group.total), 0)
  const receiptCount = categoryGroups.reduce((sum, group) => sum + group.receipt_count, 0)

  const hasAnySpending = trendGroups.length > 0 || categoryGroups.length > 0
  const loading = trend.isPending || byCategory.isPending

  return (
    <div className="dashboard">
      <div className="dashboard-main">
        <h1>Dashboard</h1>

        {!loading && !hasAnySpending && (
          <section className="card empty-state">
            <h2>No spending yet</h2>
            <p>
              <Link to="/receipts">Upload a receipt</Link> or forward one by email to get started.
            </p>
          </section>
        )}

        {hasAnySpending && (
          <section className="card">
            <h2>Monthly spending</h2>
            <p className="subtitle">
              Last {MONTHS_SHOWN} months{trendCurrency && ` · ${trendCurrency}`} · this month so far{' '}
              {formatMoney(monthRows[monthRows.length - 1].value, trendCurrency)}
            </p>
            <MonthlyChart rows={monthRows} currency={trendCurrency} />
            <OtherCurrencies groups={trendGroups} shown={trendCurrency} />
          </section>
        )}

        <div className="filter-row" role="group" aria-label="Time period">
          {(Object.keys(PERIODS) as Period[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={period === key}
              onClick={() => setPeriod(key)}
            >
              {PERIODS[key]}
            </button>
          ))}
        </div>

        <div className={byCategory.isPlaceholderData ? 'refreshing' : undefined}>
          <section className="hero">
            <span className="hero-label">Spent · {PERIODS[period].toLowerCase()}</span>
            <span className="hero-value">{formatMoney(periodTotal, currency)}</span>
            <span className="muted">
              {receiptCount} {receiptCount === 1 ? 'receipt' : 'receipts'}
            </span>
          </section>

          <section className="card">
            <h2>Spending by category</h2>
            {categoryRows.length ? (
              <>
                <CategoryChart rows={categoryRows} currency={currency} />
                <OtherCurrencies groups={categoryGroups} shown={currency} />
              </>
            ) : (
              <p className="muted">No spending in this period.</p>
            )}
          </section>
        </div>
        {byCategory.isError && <p className="error-text">{byCategory.error.message}</p>}
      </div>

      <aside className="dashboard-side">
        <section className="card">
          <h2>
            Needs review{' '}
            {flagged.data && flagged.data.length > 0 && (
              <span className="count">{flagged.data.length}</span>
            )}
          </h2>
          {flagged.data?.length === 0 && <p className="muted">Nothing to review.</p>}
          <ul className="flagged-list">
            {flagged.data?.slice(0, 5).map((receipt) => (
              <li key={receipt.id}>
                <Link to={`/receipts/${receipt.id}`}>
                  {receipt.vendor ?? receipt.original_filename}
                </Link>
                <span className="muted">
                  {' '}
                  · {formatDate(receipt.purchase_date)} · {formatMoney(receipt.total, receipt.currency)}
                </span>
                <div>
                  <OpenFlagBadges flags={receipt.flags} />
                </div>
              </li>
            ))}
          </ul>
          {flagged.data && flagged.data.length > 5 && (
            <Link to="/receipts?review=1">See all {flagged.data.length}</Link>
          )}
        </section>
        <ChatPanel />
      </aside>
    </div>
  )
}
