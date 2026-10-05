import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { errorResponse, makeReceipt, mockApi, renderWithProviders } from '../test/utils'
import { ReceiptsPage } from './ReceiptsPage'

const flagged = makeReceipt({
  id: 2,
  vendor: 'Fresh Mart',
  total: '95.00',
  needs_review: true,
  flags: [
    {
      id: 7,
      kind: 'anomaly',
      code: 'high_for_category',
      message: 'Unusually high.',
      related_receipt_id: null,
      dismissed_at: null,
    },
  ],
})

it('lists receipts with their review status', async () => {
  mockApi({ 'GET /receipts': [makeReceipt(), flagged] })
  renderWithProviders(<ReceiptsPage />)

  expect(await screen.findByRole('link', { name: 'Corner Cafe' })).toHaveAttribute(
    'href',
    '/receipts/1',
  )
  expect(screen.getByText('$8.37')).toBeInTheDocument()
  expect(screen.getByText('Unusual charge')).toBeInTheDocument()
})

it('filters to receipts that need review', async () => {
  const { calls } = mockApi({ 'GET /receipts': [flagged] })
  renderWithProviders(<ReceiptsPage />)

  await userEvent.click(screen.getByRole('button', { name: 'Needs review' }))

  await waitFor(() => expect(calls.at(-1)?.search).toBe('?needs_review=true'))
})

it('uploads a file and links to the new receipt', async () => {
  const { calls } = mockApi({
    'GET /receipts': [],
    'POST /receipts': makeReceipt({ id: 42 }),
  })
  renderWithProviders(<ReceiptsPage />)

  const file = new File(['fake'], 'lunch.png', { type: 'image/png' })
  await userEvent.upload(screen.getByLabelText('Upload receipts'), file)

  expect(await screen.findByRole('link', { name: 'Added' })).toHaveAttribute('href', '/receipts/42')
  const upload = calls.find((call) => call.method === 'POST')
  expect(upload).toBeDefined()
  expect((upload!.init!.body as FormData).get('file')).toBe(file)
})

it('shows why an upload was rejected', async () => {
  mockApi({
    'GET /receipts': [],
    'POST /receipts': () =>
      errorResponse(415, 'Unsupported file type. Upload a JPEG, PNG, or WebP image, or a PDF.'),
  })
  renderWithProviders(<ReceiptsPage />)

  await userEvent.upload(
    screen.getByLabelText('Upload receipts'),
    new File(['x'], 'notes.png', { type: 'image/png' }),
  )

  expect(await screen.findByText(/Unsupported file type/)).toBeInTheDocument()
})
