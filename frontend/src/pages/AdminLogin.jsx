/* Admin sign-in. Same endpoint as the customer login - there is only one login.
 *
 * What makes somebody an admin is the role on their account, checked by the
 * server on every single admin request. This page cannot grant anything: if you
 * sign in here with a customer account you get a customer session, and the code
 * box below changes nothing about that.
 *
 * So why have it? It is a signpost, not a gate - a separate, obviously different
 * door for a different job, which is worth having when one of the two contexts
 * can freeze accounts and adjust balances. The real check is server-side.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function AdminLogin() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const user = await login(email, password)
      // Say plainly what happened rather than dropping them somewhere confusing.
      if (user.role !== 'ADMIN') {
        setError('That account is not an admin. You are signed in as a customer.')
        setBusy(false)
        return
      }
      navigate('/admin')
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="theme-admin">
      <div className="card narrow">
        <h1>Admin sign-in</h1>
        <p className="hint">
          For staff accounts. Your role comes from your account, not from this
          page — the server checks it on every admin action.
        </p>
        <form onSubmit={handleSubmit}>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Signing in...' : 'Sign in'}</button>
        </form>
        <p>
          Need a staff account? <Link to="/admin/register">Register with the team code</Link>.
        </p>
      </div>
      <Link className="corner-link" to="/login">← Customer login</Link>
    </div>
  )
}
