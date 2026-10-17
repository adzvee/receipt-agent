import { Link } from 'react-router-dom'
import type { Receipt } from '../api'
import { categoryLabel, formatDate, formatMoney } from '../format'
import { OpenFlagBadges } from './FlagBadge'

export function ReceiptTable({ receipts }: { receipts: Receipt[] }) {
  return (
    <div className="table-scroll">
      <table className="receipt-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Vendor</th>
            <th>Category</th>
            <th className="num">Total</th>
            <th>Review</th>
          </tr>
        </thead>
        <tbody>
          {receipts.map((receipt) => {
            const hasOpenFlags = receipt.flags.some((flag) => !flag.dismissed_at)
            return (
              <tr key={receipt.id}>
                <td className="nowrap">{formatDate(receipt.purchase_date)}</td>
                <td>
                  <Link to={`/receipts/${receipt.id}`}>
                    {receipt.vendor ?? receipt.original_filename}
                  </Link>
                  {receipt.source === 'email' && <span className="muted"> · via email</span>}
                </td>
                <td>{categoryLabel(receipt.category)}</td>
                <td className="num">{formatMoney(receipt.total, receipt.currency)}</td>
                <td>
                  {hasOpenFlags ? (
                    <OpenFlagBadges flags={receipt.flags} />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
