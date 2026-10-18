import { FileText, Mail } from 'lucide-react'
import { useState } from 'react'
import { receiptThumbnailUrl, type Receipt } from '../api'

/** A small preview: the photo itself, or an icon for PDFs and forwarded emails. */
export function ReceiptThumbnail({ receipt }: { receipt: Receipt }) {
  const [failed, setFailed] = useState(false)
  const isPhoto = receipt.content_type.startsWith('image/')

  if (isPhoto && !failed) {
    return (
      <img
        className="thumbnail"
        src={receiptThumbnailUrl(receipt.id)}
        alt="" // decorative: the vendor name next to it says what it is
        loading="lazy"
        width={36}
        height={48}
        onError={() => setFailed(true)}
      />
    )
  }
  const Icon = receipt.content_type === 'text/plain' ? Mail : FileText
  return (
    <span className="thumbnail thumbnail-icon" aria-hidden="true">
      <Icon size={18} />
    </span>
  )
}
