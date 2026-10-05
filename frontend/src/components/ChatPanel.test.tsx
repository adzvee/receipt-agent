import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { errorResponse, mockApi, renderWithProviders } from '../test/utils'
import { ChatPanel } from './ChatPanel'

it('asks a question and shows the answer with how it was found', async () => {
  mockApi({
    'POST /chat': {
      answer: 'You spent **$125.50** on food in September.',
      tool_calls: [
        { name: 'spending_summary', arguments: { categories: ['groceries', 'dining'] } },
      ],
    },
  })
  renderWithProviders(<ChatPanel />)

  await userEvent.type(screen.getByLabelText('Question'), 'Food in September?')
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))

  expect(await screen.findByText('$125.50')).toBeInTheDocument()
  expect(screen.getByText('Food in September?')).toBeInTheDocument()
  expect(
    screen.getByText('Spending summary · categories: groceries, dining'),
  ).toBeInTheDocument()
})

it('sends earlier turns as history for follow-up questions', async () => {
  const { calls } = mockApi({ 'POST /chat': { answer: '$20.', tool_calls: [] } })
  renderWithProviders(<ChatPanel />)

  await userEvent.type(screen.getByLabelText('Question'), 'Dining in September?{Enter}')
  await screen.findByText('$20.')
  await userEvent.type(screen.getByLabelText('Question'), 'And October?{Enter}')
  await waitFor(() => expect(calls).toHaveLength(2))

  expect(JSON.parse(String(calls[1].init?.body))).toEqual({
    question: 'And October?',
    history: [
      { role: 'user', content: 'Dining in September?' },
      { role: 'assistant', content: '$20.' },
    ],
  })
})

it('a suggestion button asks that question', async () => {
  const { calls } = mockApi({ 'POST /chat': { answer: 'Nothing yet.', tool_calls: [] } })
  renderWithProviders(<ChatPanel />)

  await userEvent.click(screen.getByRole('button', { name: 'Which receipts need review?' }))

  await screen.findByText('Nothing yet.')
  expect(JSON.parse(String(calls[0].init?.body)).question).toBe('Which receipts need review?')
})

it('shows the error when the assistant is unavailable', async () => {
  mockApi({
    'POST /chat': () =>
      errorResponse(503, 'The assistant is unavailable right now. Please try again in a moment.'),
  })
  renderWithProviders(<ChatPanel />)

  await userEvent.type(screen.getByLabelText('Question'), 'Hi{Enter}')

  expect(await screen.findByText(/assistant is unavailable/)).toBeInTheDocument()
})
