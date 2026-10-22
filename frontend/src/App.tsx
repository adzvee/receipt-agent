import { useMutation } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { logout, type User } from './api'
import { useCurrentUser, useSetCurrentUser } from './auth'
import { LoginPage } from './pages/LoginPage'

// Each page is loaded when first visited, so e.g. the chart library only downloads with
// the dashboard.
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const ReceiptsPage = lazy(() =>
  import('./pages/ReceiptsPage').then((m) => ({ default: m.ReceiptsPage })),
)
const AccountPage = lazy(() =>
  import('./pages/AccountPage').then((m) => ({ default: m.AccountPage })),
)
const ReceiptDetailPage = lazy(() =>
  import('./pages/ReceiptDetailPage').then((m) => ({ default: m.ReceiptDetailPage })),
)

export default function App() {
  const me = useCurrentUser()

  if (me.isPending) return <p className="muted page">Loading…</p>
  if (me.isError) return <p className="error-text page">{me.error.message}</p>
  if (!me.data) {
    return (
      <main>
        <LoginPage />
      </main>
    )
  }
  return <SignedInApp user={me.data} />
}

function SignedInApp({ user }: { user: User }) {
  const setCurrentUser = useSetCurrentUser()
  const signOut = useMutation({ mutationFn: logout, onSuccess: () => setCurrentUser(null) })

  return (
    <>
      <header className="app-header">
        <span className="brand">Receipt Agent</span>
        <nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/receipts">Receipts</NavLink>
        </nav>
        <div className="account">
          <NavLink to="/account" className="account-link">
            {user.is_demo ? 'Demo account' : user.email}
          </NavLink>
          <button type="button" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
            Log out
          </button>
        </div>
      </header>
      {user.is_demo && (
        <p className="demo-banner" role="status">
          You're exploring a demo with sample receipts. It's deleted after 24 hours.{' '}
          {user.demo_requests_left === 0
            ? 'You have no AI requests left. Create an account to keep going.'
            : `${user.demo_requests_left} AI requests (uploads and questions) left.`}
        </p>
      )}
      <main>
        <Suspense fallback={<p className="muted">Loading…</p>}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/receipts" element={<ReceiptsPage />} />
            <Route path="/receipts/:id" element={<ReceiptDetailPage />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </Suspense>
      </main>
    </>
  )
}
