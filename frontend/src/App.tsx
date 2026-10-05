import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'

// Each page is loaded when first visited, so e.g. the chart library only downloads with
// the dashboard.
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const ReceiptsPage = lazy(() =>
  import('./pages/ReceiptsPage').then((m) => ({ default: m.ReceiptsPage })),
)
const ReceiptDetailPage = lazy(() =>
  import('./pages/ReceiptDetailPage').then((m) => ({ default: m.ReceiptDetailPage })),
)

export default function App() {
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
      </header>
      <main>
        <Suspense fallback={<p className="muted">Loading…</p>}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/receipts" element={<ReceiptsPage />} />
            <Route path="/receipts/:id" element={<ReceiptDetailPage />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </Suspense>
      </main>
    </>
  )
}
