import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { makeUser, mockApi, renderWithProviders } from '../test/utils'
import { ForwardingAddress } from './ForwardingAddress'

it('shows the address with what it is for, and copies it', async () => {
  const address = 'receipts+abc123@inbound.example.com'
  mockApi({ 'GET /auth/me': makeUser({ forwarding_address: address }) })
  const user = userEvent.setup() // installs a fake clipboard
  const writeText = vi.spyOn(navigator.clipboard, 'writeText')
  renderWithProviders(<ForwardingAddress />)

  expect(await screen.findByText(address)).toBeInTheDocument()
  expect(screen.getByText(/Forward receipts from Uber, Amazon/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Copy' }))

  expect(writeText).toHaveBeenCalledWith(address)
  expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
})

it('explains why a demo account has no address', async () => {
  mockApi({ 'GET /auth/me': makeUser({ is_demo: true, forwarding_address: null }) })
  renderWithProviders(<ForwardingAddress />)

  expect(await screen.findByText(/Demo accounts have no forwarding address/)).toBeInTheDocument()
})
