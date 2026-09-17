import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function Login() {
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
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <div className="card narrow">
      <h1>Log in</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Logging in...' : 'Log in'}</button>
      </form>
      <p>No account yet? <Link to="/register">Register</Link></p>
      {/* TEMPORARY test hook. The transaction menu will live on the logged-in
        * dashboard; until that page exists, this is how you reach it. Delete
        * this and the public /transactions route in App.jsx together. */}
      <p><Link to="/transactions">Transaction menu (test)</Link></p>
      <p className="hint">
        Seed login: <code>aaron.forrester@example.com</code>, password
        <code>BankDemo123!</code>.
      </p>
    </div>
    {/* Staff door. Tucked in the corner because almost nobody using this is
        staff, and it should not compete with the form. */}
    <Link className="corner-link staff" to="/admin/login">Staff sign-in</Link>
    </>
  )
}
