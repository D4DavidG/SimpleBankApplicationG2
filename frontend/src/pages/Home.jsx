/* Brief 7.1: the home page is a landing page with a way through to the rest.
 *
 * The account list itself lives on /accounts, so the nav's Accounts tab has
 * somewhere of its own to go and this page does not have to be two things. */
import { Link } from 'react-router-dom'
import { useAuth } from '../context/auth-context'
import { formatCents } from '../lib/money'

export default function Home() {
  const { user, accounts, isAdmin } = useAuth()

  // Summing cents, never dollars. Integers stay exact; the divide by 100 happens
  // once, inside formatCents, on the way to the screen.
  const total = accounts.reduce((sum, account) => sum + account.balance, 0)

  return (
    <div>
      <h1>Welcome back, {user.name}</h1>

      {accounts.length > 0 ? (
        <div className="card">
          <p className="hint">Across {accounts.length} account
            {accounts.length === 1 ? '' : 's'}</p>
          <p className="total">{formatCents(total)}</p>
        </div>
      ) : (
        <div className="card">
          <p>You do not have a bank account yet.</p>
        </div>
      )}

      <div className="actions">
        {accounts.length > 0 && <Link className="action" to="/accounts">View accounts</Link>}
        <Link className="action" to="/accounts/new">Open an account</Link>
        {accounts.length > 0 && <Link className="action" to="/transfer">Transfer money</Link>}
        <Link className="action" to="/profile">My details</Link>
        {isAdmin && <Link className="action" to="/admin">Admin tools</Link>}
      </div>
    </div>
  )
}
