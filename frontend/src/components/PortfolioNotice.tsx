import { Info } from 'lucide-react'

/** Shown where people sign up and on the dashboard. */
export function PortfolioNotice() {
  return (
    <p className="notice" role="note">
      <Info aria-hidden="true" size={18} />
      <span>
        <strong>This is a portfolio project.</strong> Please don't upload real or sensitive
        receipts. Try the demo, or use made-up receipts.
      </span>
    </p>
  )
}
