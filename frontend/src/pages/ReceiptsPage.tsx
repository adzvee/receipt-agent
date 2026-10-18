import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { listReceipts } from '../api'
import { ForwardingAddress } from '../components/ForwardingAddress'
import { ReceiptTable } from '../components/ReceiptTable'
import { UploadDropzone } from '../components/UploadDropzone'

export function ReceiptsPage() {
  // The filter lives in the URL (?review=1) so the view can be linked to and survives reload.
  const [searchParams, setSearchParams] = useSearchParams()
  const needsReview = searchParams.get('review') === '1'

  const receipts = useQuery({
    queryKey: ['receipts', { needsReview }],
    queryFn: () => listReceipts({ needsReview }),
  })

  return (
    <div className="page">
      <h1>Receipts</h1>
      <UploadDropzone />
      <ForwardingAddress />

      <div className="filter-row" role="group" aria-label="Filter receipts">
        <button type="button" aria-pressed={!needsReview} onClick={() => setSearchParams({})}>
          All
        </button>
        <button
          type="button"
          aria-pressed={needsReview}
          onClick={() => setSearchParams({ review: '1' })}
        >
          Needs review
        </button>
      </div>

      {receipts.isPending && <p className="muted">Loading…</p>}
      {receipts.isError && <p className="error-text">{receipts.error.message}</p>}
      {receipts.data?.length === 0 && (
        <p className="muted">{needsReview ? 'Nothing needs review.' : 'No receipts yet.'}</p>
      )}
      {receipts.data && receipts.data.length > 0 && <ReceiptTable receipts={receipts.data} />}
    </div>
  )
}
