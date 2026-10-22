import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import type { Receipt, User } from '../api'
import { createQueryClient } from '../queryClient'

/** Render with the same providers as the app, at a given URL. */
export function renderWithProviders(ui: ReactElement, { route = '/', path = '*' } = {}) {
  const queryClient = createQueryClient({ retry: false })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

type Handler = (init: RequestInit | undefined, url: URL) => unknown

/**
 * Fake the backend: each key is "METHOD /path" (without /api). A handler returns a JSON
 * body, or a Response for errors. Every request is recorded in `calls`.
 */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; path: string; search: string; init?: RequestInit }[] = []
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    const path = url.pathname.replace(/^\/api/, '')
    calls.push({ method, path, search: url.search, init })
    const route = routes[`${method} ${path}`]
    if (route === undefined) return new Response('{"detail":"Not mocked"}', { status: 404 })
    const body = typeof route === 'function' ? (route as Handler)(init, url) : route
    if (body instanceof Response) return body
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls }
}

export function errorResponse(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status })
}

/** A fake receipt; override any field. */
export function makeReceipt(overrides: Partial<Receipt> = {}): Receipt {
  return {
    id: 1,
    created_at: '2026-09-14T10:00:00Z',
    source: 'upload',
    original_filename: 'receipt.png',
    content_type: 'image/png',
    status: 'extracted',
    extraction_error: null,
    vendor: 'Corner Cafe',
    purchase_date: '2026-09-14',
    currency: 'USD',
    subtotal: '7.75',
    tax: '0.62',
    tip: null,
    total: '8.37',
    payment_method: 'Visa ending 4242',
    line_items: [
      { description: 'Latte', quantity: '1.000', unit_price: '4.50', amount: '4.50' },
      { description: 'Croissant', quantity: '1.000', unit_price: '3.25', amount: '3.25' },
    ],
    category: 'dining',
    category_source: 'llm',
    category_reason: "It's a café.",
    flags: [],
    needs_review: false,
    ...overrides,
  }
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    email: 'you@example.com',
    is_demo: false,
    forwarding_address: null,
    demo_requests_left: null,
    receipts_left_today: 5,
    questions_left_today: 10,
    ...overrides,
  }
}
