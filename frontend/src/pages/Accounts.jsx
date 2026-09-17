/* The account list. Reached from the nav's Accounts tab and from Home.
 *
 * The accounts come from the auth context rather than a fetch here, because the
 * nav needs the same list to decide whether to show its tab. */
import { Link } from 'react-router-dom'
import { useAuth } from '../context/auth-context'
import { formatCents } from '../lib/money'

export default function Accounts() {
  const { accounts } = useAuth()

  if (accounts.length === 0) {
    return (
      <div className="card">
        <h1>Your accounts</h1>
        <p>Nothing here yet. <Link to="/accounts/new">Open an account</Link>.</p>
      </div>
    )
  }

  return (
    <div>
      <h1>Your accounts</h1>
      <ul className="account-list">
        {accounts.map((account) => (
          <li key={account.accountId} className="card">
            <Link to={`/accounts/${account.accountId}`}>
              <strong>{account.accountType}</strong> #{account.accountId}
            </Link>
            {account.status === 'FROZEN' && <span className="badge">FROZEN</span>}
            {/* Divide by 100 to display, never to calculate. */}
            <span className="balance">{formatCents(account.balance)}</span>
          </li>
        ))}
      </ul>
      <p><Link to="/accounts/new">Open another account</Link></p>
    </div>
  )
}
