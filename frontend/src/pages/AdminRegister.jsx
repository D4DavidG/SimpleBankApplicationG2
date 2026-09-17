/* Registering a staff account, using the team's shared admin code.
 *
 * The code is NOT checked here. It is sent to the server as `adminCode` and
 * compared against a value only the server has (BANK_ADMIN_CODE in .env). That
 * matters: a check written in this file would ship inside the JavaScript bundle,
 * where anyone can read it with Ctrl+U, and it would stop nobody. Sending it and
 * letting the server decide means the code never exists in the browser except as
 * whatever the person typed.
 *
 * A wrong code is a 403 and creates no user at all, so a failed attempt does not
 * burn the email address.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function AdminRegister() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', adminCode: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await register(form.name, form.email, form.password, form.adminCode)
      navigate('/admin')
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="theme-admin">
      <div className="card narrow">
        <h1>Register a staff account</h1>
        <p className="hint">
          You need the team code. Without it this creates an ordinary customer,
          so use the <Link to="/register">customer form</Link> if that is what you meant.
        </p>
        <form onSubmit={handleSubmit}>
          <label>
            Name
            <input value={form.name} onChange={update('name')} required />
          </label>
          <label>
            Email
            <input type="email" value={form.email} onChange={update('email')} required />
          </label>
          <label>
            Password
            <input type="password" value={form.password} onChange={update('password')} required />
          </label>
          <label>
            Team code
            <input type="password" value={form.adminCode} onChange={update('adminCode')}
                   autoComplete="off" required />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Creating...' : 'Create staff account'}</button>
        </form>
        <p>Already have one? <Link to="/admin/login">Admin sign-in</Link>.</p>
      </div>
      <Link className="corner-link" to="/register">← Customer registration</Link>
    </div>
  )
}
