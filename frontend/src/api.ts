// Typed access to the FastAPI backend. Types mirror backend/app/schemas.py.
// Money arrives as strings (e.g. "8.37") so no precision is lost; convert only to display.

export type FlagKind = 'extraction' | 'validation' | 'duplicate' | 'anomaly'

export interface Flag {
  id: number
  kind: FlagKind
  code: string
  message: string
  related_receipt_id: number | null
  dismissed_at: string | null
}

export interface LineItem {
  description: string
  quantity: string | null
  unit_price: string | null
  amount: string
}

export interface Receipt {
  id: number
  created_at: string
  source: 'upload' | 'email'
  original_filename: string
  content_type: string
  status: 'extracted' | 'failed'
  extraction_error: string | null
  vendor: string | null
  purchase_date: string | null
  currency: string | null
  subtotal: string | null
  tax: string | null
  tip: string | null
  total: string | null
  payment_method: string | null
  line_items: LineItem[]
  category: string | null
  category_source: 'llm' | 'vendor_history' | 'user' | null
  category_reason: string | null
  flags: Flag[]
  needs_review: boolean
}

export interface SpendingGroup {
  currency: string | null
  total: string
  receipt_count: number
  category?: string
  month?: string
  vendor?: string
}

export interface SpendingQuery {
  group_by?: 'none' | 'category' | 'vendor' | 'month'
  start_date?: string
  end_date?: string
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
}

export interface ChatResponse {
  answer: string
  tool_calls: ToolCall[]
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, init)
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return (await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    // FastAPI errors look like {"detail": "..."} or {"detail": [{"msg": "..."}]}.
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg
  } catch {
    // not JSON
  }
  return `Request failed (${response.status})`
}

function jsonBody(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export function listReceipts(options: { needsReview?: boolean } = {}): Promise<Receipt[]> {
  const query = options.needsReview ? '?needs_review=true' : ''
  return request(`/receipts${query}`)
}

export function getReceipt(id: number): Promise<Receipt> {
  return request(`/receipts/${id}`)
}

export function uploadReceipt(file: File): Promise<Receipt> {
  const form = new FormData()
  form.append('file', file)
  return request('/receipts', { method: 'POST', body: form })
}

export function updateCategory(id: number, category: string): Promise<Receipt> {
  return request(`/receipts/${id}`, jsonBody('PATCH', { category }))
}

export function dismissFlag(receiptId: number, flagId: number): Promise<Receipt> {
  return request(`/receipts/${receiptId}/flags/${flagId}/dismiss`, { method: 'POST' })
}

export function getCategories(): Promise<string[]> {
  return request('/receipts/categories')
}

export function getSpending(query: SpendingQuery = {}): Promise<{ groups: SpendingGroup[] }> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value) params.set(key, value)
  }
  const search = params.toString()
  return request(`/stats/spending${search ? `?${search}` : ''}`)
}

export function askQuestion(question: string, history: ChatTurn[]): Promise<ChatResponse> {
  return request('/chat', jsonBody('POST', { question, history }))
}

export function receiptFileUrl(id: number): string {
  return `${BASE}/receipts/${id}/file`
}
