import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import type { Flag } from '../api'
import { makeReceipt, mockApi, renderWithProviders } from '../test/utils'
import { ReceiptDetailPage } from './ReceiptDetailPage'

const duplicateFlag: Flag = {
  id: 9,
  kind: 'duplicate',
  code: 'duplicate_file',
  message: 'This is the same file as receipt #3.',
  related_receipt_id: 3,
  dismissed_at: null,
}

function renderDetail() {
  return renderWithProviders(<ReceiptDetailPage />, { route: '/receipts/5', path: '/receipts/:id' })
}

it('shows the extracted details and line items', async () => {
  mockApi({ 'GET /receipts/5': makeReceipt({ id: 5 }), 'GET /receipts/categories': ['dining'] })
  renderDetail()

  expect(await screen.findByRole('heading', { name: 'Corner Cafe' })).toBeInTheDocument()
  expect(screen.getByText('$8.37')).toBeInTheDocument()
  expect(screen.getByText('Croissant')).toBeInTheDocument()
  expect(screen.getByText("Suggested by AI: It's a café.")).toBeInTheDocument()
})

it('dismissing a flag sends it to the API and removes it', async () => {
  const flagged = makeReceipt({ id: 5, flags: [duplicateFlag], needs_review: true })
  const { calls } = mockApi({
    'GET /receipts/5': flagged,
    'GET /receipts/categories': ['dining'],
    'POST /receipts/5/flags/9/dismiss': {
      ...flagged,
      flags: [{ ...duplicateFlag, dismissed_at: '2026-10-04T12:00:00Z' }],
      needs_review: false,
    },
  })
  renderDetail()

  expect(await screen.findByText('This is the same file as receipt #3.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'View receipt #3' })).toHaveAttribute(
    'href',
    '/receipts/3',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

  await waitFor(() =>
    expect(screen.queryByText('This is the same file as receipt #3.')).not.toBeInTheDocument(),
  )
  expect(calls.some((call) => call.method === 'POST')).toBe(true)
})

it('changing the category saves it', async () => {
  const { calls } = mockApi({
    'GET /receipts/5': makeReceipt({ id: 5 }),
    'GET /receipts/categories': ['dining', 'groceries'],
    'PATCH /receipts/5': makeReceipt({ id: 5, category: 'groceries', category_source: 'user' }),
  })
  renderDetail()

  const select = await screen.findByLabelText('Category')
  await waitFor(() => expect(select).toBeEnabled())
  await userEvent.selectOptions(select, 'groceries')

  expect(await screen.findByText('Set by you')).toBeInTheDocument()
  const patch = calls.find((call) => call.method === 'PATCH')
  expect(JSON.parse(String(patch?.init?.body))).toEqual({ category: 'groceries' })
})

it('shows emailed receipts as plain text', async () => {
  mockApi({
    'GET /receipts/5': makeReceipt({ id: 5, source: 'email', content_type: 'text/plain' }),
    'GET /receipts/categories': ['dining'],
    'GET /receipts/5/file': () => new Response('<b>Total</b> $13.23'),
  })
  renderDetail()

  const preview = await screen.findByText('<b>Total</b> $13.23')
  expect(preview.tagName).toBe('PRE')
  expect(screen.getByText(/Forwarded by email/)).toBeInTheDocument()
})
