import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { login, register, startDemo } from '../api'
import { useSetCurrentUser } from '../auth'

type Mode = 'login' | 'register'

export function LoginPage() {
  const setCurrentUser = useSetCurrentUser()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const submit = useMutation({
    mutationFn: () => (mode === 'login' ? login(email, password) : register(email, password)),
    onSuccess: setCurrentUser,
  })
  const demo = useMutation({ mutationFn: startDemo, onSuccess: setCurrentUser })

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    submit.mutate()
  }

  const busy = submit.isPending || demo.isPending

  return (
    <div className="login">
      <h1>Receipt Agent</h1>
      <p className="subtitle">
        Turn receipt photos, PDFs, and forwarded emails into categorized, searchable spending.
      </p>

      <section className="card demo-card">
        <h2>Just looking?</h2>
        <p>Explore a demo account with two months of sample receipts. No sign-up needed.</p>
        <button type="button" className="primary" onClick={() => demo.mutate()} disabled={busy}>
          {demo.isPending ? 'Setting up your demo…' : 'Try the demo'}
        </button>
        {demo.isError && <p className="error-text">{demo.error.message}</p>}
      </section>

      <section className="card">
        <h2>{mode === 'login' ? 'Log in' : 'Create an account'}</h2>

        <form onSubmit={onSubmit} className="login-form">
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
              minLength={8}
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {mode === 'register' && <p className="muted small">At least 8 characters.</p>}
          {submit.isError && <p className="error-text">{submit.error.message}</p>}
          <button type="submit" disabled={busy}>
            {mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>
        <p className="muted small switch-mode">
          {mode === 'login' ? 'New here? ' : 'Already have an account? '}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              submit.reset()
            }}
          >
            {mode === 'login' ? 'Create an account' : 'Log in instead'}
          </button>
        </p>
      </section>
    </div>
  )
}
