import { Mail } from 'lucide-react'
import { useState } from 'react'
import { useCurrentUser } from '../auth'

/** The user's personal address for forwarding receipt emails, with a copy button. */
export function ForwardingAddress() {
  const user = useCurrentUser().data
  const [copied, setCopied] = useState(false)
  if (!user) return null

  const address = user.forwarding_address
  async function copy() {
    if (!address) return
    await navigator.clipboard.writeText(address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="forwarding" aria-label="Email forwarding">
      <Mail aria-hidden="true" size={20} className="forwarding-icon" />
      <div>
        <h2>Forward receipt emails</h2>
        {address ? (
          <>
            <p className="muted">
              Forward receipts from Uber, Amazon, or any store to your own address and they're
              added automatically.
            </p>
            <p className="forwarding-address">
              <strong className="selectable">{address}</strong>
              <button type="button" onClick={copy}>
                {copied ? 'Copied' : 'Copy'}
              </button>
            </p>
          </>
        ) : (
          <p className="muted">
            {user.is_demo
              ? 'Demo accounts have no forwarding address. Create an account to get your own, ' +
                'and forward receipts from Uber, Amazon, or any store to add them automatically.'
              : "Email forwarding isn't set up on this server yet. Once it is, you'll get your " +
                'own address here for forwarding receipts from Uber, Amazon, or any store.'}
          </p>
        )}
      </div>
    </section>
  )
}
