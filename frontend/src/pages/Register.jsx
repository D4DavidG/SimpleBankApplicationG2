/* The brief's "Create Account Page" (7.2) is two things in this API: registering
 * a user (here) and opening a bank account for them (OpenAccount.jsx). There is
 * deliberately no role field - the backend would ignore it anyway. */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await register(form.name, form.email, form.password)
      navigate('/accounts/new') // a new user has no bank account yet
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <div className="card narrow">
      <h1>Register</h1>
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
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Creating...' : 'Create account'}</button>
      </form>
      <p>Already registered? <Link to="/login">Log in</Link></p>
    </div>
    <Link className="corner-link" to="/admin/register">Staff registration</Link>
    </>
  )
}
