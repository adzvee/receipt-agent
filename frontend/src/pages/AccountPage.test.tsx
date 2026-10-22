import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import App from '../App'
import { errorResponse, makeUser, mockApi, renderWithProviders } from '../test/utils'

it('deletes the account with the password, then shows the login page', async () => {
  const { calls } = mockApi({
    'GET /auth/me': makeUser(),
    'DELETE /auth/me': () => new Response(null, { status: 204 }),
  })
  renderWithProviders(<App />, { route: '/account' })

  const button = await screen.findByRole('button', { name: 'Delete my account' })
  expect(button).toBeDisabled() // until the checkbox is ticked
  await userEvent.type(screen.getByLabelText('Password'), 'my password')
  await userEvent.click(screen.getByLabelText(/all my receipts will be deleted/))
  await userEvent.click(button)

  expect(await screen.findByRole('button', { name: 'Try the demo' })).toBeInTheDocument()
  const deletion = calls.find((call) => call.method === 'DELETE')
  expect(JSON.parse(String(deletion?.init?.body))).toEqual({ password: 'my password' })
})

it('shows why a deletion was refused', async () => {
  mockApi({
    'GET /auth/me': makeUser(),
    'DELETE /auth/me': () => errorResponse(403, "That password isn't right."),
  })
  renderWithProviders(<App />, { route: '/account' })

  await userEvent.type(await screen.findByLabelText('Password'), 'wrong')
  await userEvent.click(screen.getByLabelText(/all my receipts will be deleted/))
  await userEvent.click(screen.getByRole('button', { name: 'Delete my account' }))

  expect(await screen.findByText("That password isn't right.")).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Account' })).toBeInTheDocument()
})

it('demo accounts delete without a password', async () => {
  const { calls } = mockApi({
    'GET /auth/me': makeUser({ is_demo: true }),
    'DELETE /auth/me': () => new Response(null, { status: 204 }),
  })
  renderWithProviders(<App />, { route: '/account' })

  await userEvent.click(await screen.findByLabelText(/all my receipts will be deleted/))
  expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Delete my account' }))

  await waitFor(() => expect(calls.some((call) => call.method === 'DELETE')).toBe(true))
  const deletion = calls.find((call) => call.method === 'DELETE')
  expect(JSON.parse(String(deletion?.init?.body))).toEqual({ password: null })
})

it("shows what is left of today's limits", async () => {
  mockApi({ 'GET /auth/me': makeUser({ receipts_left_today: 2, questions_left_today: 1 }) })
  renderWithProviders(<App />, { route: '/account' })

  expect(
    await screen.findByText(/add 2 more receipts and ask 1 more question/),
  ).toBeInTheDocument()
})
