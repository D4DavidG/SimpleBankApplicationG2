/* Admin sign-in. Same endpoint as the customer login - there is only one login.
 *
 * READ THIS BEFORE TRUSTING THE CODE BOX. The team code here is a speed bump,
 * not a security control, and it is checked in the browser because there is
 * nothing else it could be: `POST /api/auth/login` takes an email and a
 * password and nothing more. Anyone can read the code out of this bundle, and
 * anyone who skips this page and signs in at /login gets exactly the same
 * session.
 *
 * That is fine, because the code is not what protects anything. What makes
 * somebody an admin is the role on their account, which the server re-reads and
 * re-checks on every single admin request. Typing the right code with a customer
 * account gets you a customer session; typing nothing at all with an admin
 * account still gets you an admin one.
 *
 * What it is good for: making the staff door a deliberate act rather than a
 * stumble, which is worth something when one of these two contexts can freeze
 * accounts and adjust balances.
 *
 * On /admin/register the code is a real check, because that one is sent to the
 * server and compared there. See AdminRegister.jsx.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

// In the bundle, and therefore public. See the note at the top of this file for
// why that is acceptable here and would not be on the register page.
const TEAM_CODE = 'Group2Rules!'

export default function AdminLogin() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [teamCode, setTeamCode] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    if (teamCode !== TEAM_CODE) {
      setError('That is not the team code.')
      return
    }
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
    <div className="theme-admin admin-page">
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
          <label>
            Team code
            <input type="password" value={teamCode} autoComplete="off"
                   onChange={(e) => setTeamCode(e.target.value)} required />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Signing in...' : 'Sign in'}</button>
        </form>
        <p>
          Need a staff account? <Link to="/admin/register">Register with the team code</Link>.
        </p>
      </div>
      <Link className="corner-link customer" to="/login">← Customer login</Link>
    </div>
  )
}
