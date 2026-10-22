import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { deleteAccount } from '../api'
import { useCurrentUser, useSetCurrentUser } from '../auth'
import { ForwardingAddress } from '../components/ForwardingAddress'

export function AccountPage() {
  const user = useCurrentUser().data
  const setCurrentUser = useSetCurrentUser()
  const [password, setPassword] = useState('')
  const [confirmed, setConfirmed] = useState(false)

  const remove = useMutation({
    mutationFn: () => deleteAccount(user?.is_demo ? null : password),
    onSuccess: () => setCurrentUser(null), // back to the login page
  })

  if (!user) return null

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    remove.mutate()
  }

  return (
    <div className="page account-page">
      <h1>Account</h1>

      <section className="card">
        <h2>{user.is_demo ? 'Demo account' : user.email}</h2>
        <p className="muted">
          Today you can add {user.receipts_left_today} more{' '}
          {user.receipts_left_today === 1 ? 'receipt' : 'receipts'} and ask{' '}
          {user.questions_left_today} more{' '}
          {user.questions_left_today === 1 ? 'question' : 'questions'}. Limits reset at midnight
          UTC.
        </p>
      </section>

      <section className="card">
        <ForwardingAddress />
      </section>

      <section className="card danger-zone">
        <h2>Delete account</h2>
        <p>
          Permanently deletes your account, every receipt and uploaded file, and your
          forwarding address. This can't be undone.
        </p>
        <form onSubmit={onSubmit} className="delete-form">
          {!user.is_demo && (
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
          )}
          <label className="checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            I understand all my receipts will be deleted
          </label>
          {remove.isError && <p className="error-text">{remove.error.message}</p>}
          <button type="submit" className="danger" disabled={!confirmed || remove.isPending}>
            {remove.isPending ? 'Deleting…' : 'Delete my account'}
          </button>
        </form>
      </section>
    </div>
  )
}
