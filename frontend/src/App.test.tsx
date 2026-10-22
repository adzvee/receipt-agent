import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import App from './App'
import { errorResponse, makeUser, mockApi, renderWithProviders } from './test/utils'

const loggedOut = () => errorResponse(401, 'Please log in.')

it('shows the login page when nobody is logged in', async () => {
  mockApi({ 'GET /auth/me': loggedOut })
  renderWithProviders(<App />)

  expect(await screen.findByRole('button', { name: 'Try the demo' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument()
  expect(screen.getByRole('note')).toHaveTextContent(
    "This is a portfolio project. Please don't upload real or sensitive receipts.",
  )
})

it('logs in and shows the app', async () => {
  const { calls } = mockApi({
    'GET /auth/me': loggedOut,
    'POST /auth/login': makeUser({ email: 'you@example.com' }),
    'GET /stats/spending': { groups: [] },
    'GET /receipts': [],
  })
  renderWithProviders(<App />)

  await userEvent.type(await screen.findByLabelText('Email'), 'you@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'a long enough password')
  await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

  expect(await screen.findByText('you@example.com')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  const loginCall = calls.find((call) => call.path === '/auth/login')
  expect(JSON.parse(String(loginCall?.init?.body))).toEqual({
    email: 'you@example.com',
    password: 'a long enough password',
  })
})

it('shows why a login failed', async () => {
  mockApi({
    'GET /auth/me': loggedOut,
    'POST /auth/login': () => errorResponse(401, 'Invalid email or password.'),
  })
  renderWithProviders(<App />)

  await userEvent.type(await screen.findByLabelText('Email'), 'you@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'wrong password')
  await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

  expect(await screen.findByText('Invalid email or password.')).toBeInTheDocument()
})

it('"Try the demo" opens a demo account with a banner', async () => {
  mockApi({
    'GET /auth/me': loggedOut,
    'POST /auth/demo': makeUser({ is_demo: true, demo_requests_left: 25 }),
    'GET /stats/spending': { groups: [] },
    'GET /receipts': [],
  })
  renderWithProviders(<App />)

  await userEvent.click(await screen.findByRole('button', { name: 'Try the demo' }))

  expect(await screen.findByText('Demo account')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('25 AI requests')
})

it('logging out returns to the login page', async () => {
  mockApi({
    'GET /auth/me': makeUser(),
    'POST /auth/logout': () => new Response(null, { status: 204 }),
    'GET /stats/spending': { groups: [] },
    'GET /receipts': [],
  })
  renderWithProviders(<App />)

  await userEvent.click(await screen.findByRole('button', { name: 'Log out' }))

  expect(await screen.findByRole('button', { name: 'Try the demo' })).toBeInTheDocument()
})

it('an expired session sends you back to the login page', async () => {
  mockApi({
    'GET /auth/me': makeUser(),
    'GET /stats/spending': loggedOut,
    'GET /receipts': loggedOut,
  })
  renderWithProviders(<App />)

  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Try the demo' })).toBeInTheDocument(),
  )
})

it('can switch to creating an account', async () => {
  const { calls } = mockApi({
    'GET /auth/me': loggedOut,
    'POST /auth/register': makeUser({ email: 'new@example.com' }),
    'GET /stats/spending': { groups: [] },
    'GET /receipts': [],
  })
  renderWithProviders(<App />)

  await userEvent.click(await screen.findByRole('button', { name: 'Create an account' }))
  await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'a long enough password')
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

  expect(await screen.findByText('new@example.com')).toBeInTheDocument()
  expect(calls.some((call) => call.path === '/auth/register')).toBe(true)
})
