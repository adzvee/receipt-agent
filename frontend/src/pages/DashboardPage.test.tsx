import { screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { makeReceipt, makeUser, mockApi, renderWithProviders } from '../test/utils'
import { DashboardPage } from './DashboardPage'

const ADDRESS = 'receipts+abc123@inbound.example.com'

it('shows one welcome state on an empty account', async () => {
  mockApi({
    'GET /auth/me': makeUser({ forwarding_address: ADDRESS }),
    'GET /receipts': [],
  })
  renderWithProviders(<DashboardPage />)

  expect(await screen.findByRole('button', { name: 'Upload receipt' })).toBeInTheDocument()
  expect(screen.getByRole('note')).toHaveTextContent(/portfolio project/)
  expect(await screen.findByText(ADDRESS)).toBeInTheDocument()
  expect(screen.getByText(/Uber, Amazon/)).toBeInTheDocument()
  // The chat box stays, but nothing that only makes sense with data.
  expect(screen.getByLabelText('Question')).toBeInTheDocument()
  expect(screen.queryByRole('group', { name: 'Time period' })).not.toBeInTheDocument()
  expect(screen.queryByText(/^Spent/)).not.toBeInTheDocument()
  expect(screen.queryByText('Spending by category')).not.toBeInTheDocument()
  expect(screen.queryByText('How much did I spend on food last month?')).not.toBeInTheDocument()
})

it('shows the full dashboard once there is a receipt, with a $ on zero totals', async () => {
  const { calls } = mockApi({
    'GET /auth/me': makeUser(),
    'GET /receipts': [makeReceipt()],
    'GET /stats/spending': { groups: [] }, // e.g. the receipt is from an earlier year
  })
  renderWithProviders(<DashboardPage />)

  expect(await screen.findByRole('group', { name: 'Time period' })).toBeInTheDocument()
  expect(screen.getByRole('note')).toHaveTextContent(/portfolio project/)
  expect(await screen.findByText('$0.00')).toBeInTheDocument()
  expect(screen.getByText('How much did I spend on food last month?')).toBeInTheDocument()
  expect(calls.some((call) => call.path === '/receipts' && call.search === '?limit=1')).toBe(true)
})
