import { describe, expect, it } from 'vitest'
import {
  describeToolCall,
  formatDate,
  formatMoney,
  formatMoneyCompact,
  formatMonth,
  periodRange,
  primaryCurrency,
  recentMonths,
} from './format'

const TODAY = new Date(2026, 9, 4) // Oct 4, 2026 (months are 0-based in JS)

describe('formatMoney', () => {
  it('formats with the currency symbol', () => {
    expect(formatMoney('1234.5', 'USD')).toBe('$1,234.50')
    expect(formatMoney('20', 'EUR')).toBe('€20.00')
  })

  it('shows a dollar sign when the currency is unknown, including on zero totals', () => {
    expect(formatMoney('8.37', null)).toBe('$8.37')
    expect(formatMoney(0, null)).toBe('$0.00')
    expect(formatMoneyCompact(1200, null)).toBe('$1.2K')
  })

  it('shows a dash for a missing amount', () => {
    expect(formatMoney(null, 'USD')).toBe('—')
  })
})

describe('dates', () => {
  it('formats a calendar date without shifting it across time zones', () => {
    expect(formatDate('2026-09-01')).toBe('Sep 1, 2026')
  })

  it('shows the year on January so the year change is visible', () => {
    expect(formatMonth('2026-09')).toBe('Sep')
    expect(formatMonth('2027-01')).toBe("Jan '27")
  })

  it('computes period ranges', () => {
    expect(periodRange('this_month', TODAY)).toEqual({
      start_date: '2026-10-01',
      end_date: '2026-10-04',
    })
    expect(periodRange('last_month', TODAY)).toEqual({
      start_date: '2026-09-01',
      end_date: '2026-09-30',
    })
    expect(periodRange('last_90_days', TODAY)).toEqual({
      start_date: '2026-07-07',
      end_date: '2026-10-04',
    })
    expect(periodRange('all_time', TODAY)).toEqual({})
  })

  it('last month works across a year boundary', () => {
    expect(periodRange('last_month', new Date(2027, 0, 15))).toEqual({
      start_date: '2026-12-01',
      end_date: '2026-12-31',
    })
  })

  it('lists recent months oldest first', () => {
    expect(recentMonths(TODAY, 3)).toEqual(['2026-08', '2026-09', '2026-10'])
    expect(recentMonths(new Date(2027, 0, 5), 2)).toEqual(['2026-12', '2027-01'])
  })
})

describe('primaryCurrency', () => {
  it('picks the currency with the most spending', () => {
    const groups = [
      { currency: 'USD', total: '30.00', receipt_count: 2 },
      { currency: 'EUR', total: '50.00', receipt_count: 1 },
      { currency: 'USD', total: '25.00', receipt_count: 1 },
    ]
    expect(primaryCurrency(groups)).toBe('USD')
  })

  it('is null when there is no data', () => {
    expect(primaryCurrency([])).toBeNull()
  })
})

describe('describeToolCall', () => {
  it('describes the tool and its arguments in words', () => {
    expect(
      describeToolCall({
        name: 'spending_summary',
        arguments: { categories: ['groceries', 'dining'], start_date: '2026-09-01' },
      }),
    ).toBe('Spending summary · categories: groceries, dining · start date: 2026-09-01')
  })
})
