import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import {
  dismissFlag,
  getCategories,
  getReceipt,
  receiptFileUrl,
  updateCategory,
  type Receipt,
} from '../api'
import { FlagBadge } from '../components/FlagBadge'
import { categoryLabel, formatDate, formatMoney } from '../format'

const CATEGORY_SOURCES = {
  llm: 'Suggested by AI',
  vendor_history: 'Same as earlier receipts from this vendor',
  user: 'Set by you',
}

function FilePreview({ receipt }: { receipt: Receipt }) {
  const url = receiptFileUrl(receipt.id)
  const text = useQuery({
    queryKey: ['receipt-text', receipt.id],
    queryFn: async () => (await fetch(url)).text(),
    enabled: receipt.content_type === 'text/plain',
  })

  if (receipt.content_type.startsWith('image/')) {
    return <img className="preview" src={url} alt={`Receipt from ${receipt.vendor ?? 'unknown vendor'}`} />
  }
  if (receipt.content_type === 'application/pdf') {
    return <iframe className="preview" src={url} title="Receipt PDF" />
  }
  // Email receipts are stored as plain text and shown as text, never as HTML.
  return <pre className="preview preview-text">{text.data ?? 'Loading…'}</pre>
}

export function ReceiptDetailPage() {
  const id = Number(useParams().id)
  const queryClient = useQueryClient()

  const receipt = useQuery({ queryKey: ['receipt', id], queryFn: () => getReceipt(id) })
  const categories = useQuery({ queryKey: ['categories'], queryFn: getCategories })

  const onChanged = (updated: Receipt) => {
    queryClient.setQueryData(['receipt', id], updated)
    queryClient.invalidateQueries({ queryKey: ['receipts'] })
    queryClient.invalidateQueries({ queryKey: ['spending'] })
  }
  const changeCategory = useMutation({
    mutationFn: (category: string) => updateCategory(id, category),
    onSuccess: onChanged,
  })
  const dismiss = useMutation({
    mutationFn: (flagId: number) => dismissFlag(id, flagId),
    onSuccess: onChanged,
  })

  if (receipt.isPending) return <p className="muted page">Loading…</p>
  if (receipt.isError) return <p className="error-text page">{receipt.error.message}</p>
  const r = receipt.data
  const openFlags = r.flags.filter((flag) => !flag.dismissed_at)

  return (
    <div className="page">
      <p>
        <Link to="/receipts">← All receipts</Link>
      </p>
      <h1>{r.vendor ?? r.original_filename}</h1>
      <p className="subtitle">
        {formatDate(r.purchase_date)} · {r.source === 'email' ? 'Forwarded by email' : 'Uploaded'}
      </p>

      {openFlags.length > 0 && (
        <section className="card flags">
          <h2>Needs review</h2>
          <ul>
            {openFlags.map((flag) => (
              <li key={flag.id}>
                <FlagBadge kind={flag.kind} />
                <span>{flag.message}</span>
                {flag.related_receipt_id && (
                  <Link to={`/receipts/${flag.related_receipt_id}`}>
                    View receipt #{flag.related_receipt_id}
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() => dismiss.mutate(flag.id)}
                  disabled={dismiss.isPending}
                >
                  Dismiss
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="detail-grid">
        <FilePreview receipt={r} />

        <div>
          <section className="card">
            <dl className="fields">
              <dt>Total</dt>
              <dd className="total">{formatMoney(r.total, r.currency)}</dd>
              <dt>Subtotal</dt>
              <dd>{formatMoney(r.subtotal, r.currency)}</dd>
              <dt>Tax</dt>
              <dd>{formatMoney(r.tax, r.currency)}</dd>
              <dt>Tip</dt>
              <dd>{formatMoney(r.tip, r.currency)}</dd>
              <dt>Payment</dt>
              <dd>{r.payment_method ?? '—'}</dd>
              <dt>
                <label htmlFor="category">Category</label>
              </dt>
              <dd>
                <select
                  id="category"
                  value={r.category ?? ''}
                  disabled={!categories.data || changeCategory.isPending}
                  onChange={(event) => changeCategory.mutate(event.target.value)}
                >
                  {!r.category && <option value="">Uncategorized</option>}
                  {categories.data?.map((category) => (
                    <option key={category} value={category}>
                      {categoryLabel(category)}
                    </option>
                  ))}
                </select>
                {r.category_source && (
                  <p className="muted small">
                    {CATEGORY_SOURCES[r.category_source]}
                    {r.category_source === 'llm' && r.category_reason && `: ${r.category_reason}`}
                  </p>
                )}
              </dd>
            </dl>
            {r.status === 'failed' && (
              <p className="error-text">This receipt couldn't be read automatically.</p>
            )}
          </section>

          {r.line_items.length > 0 && (
            <section className="card">
              <h2>Items</h2>
              <table>
                <tbody>
                  {r.line_items.map((item, i) => (
                    <tr key={i}>
                      <td>
                        {item.description}
                        {item.quantity && Number(item.quantity) !== 1 && (
                          <span className="muted"> × {Number(item.quantity)}</span>
                        )}
                      </td>
                      <td className="num">{formatMoney(item.amount, r.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
