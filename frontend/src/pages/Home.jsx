/* The brief's Home Page (7.1): the logged-in user's accounts, and the way in to
 * every other screen. Functional so the rest of the pages have real account ids
 * to work against - the styling is nobody's final answer. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../lib/api'
import { formatCents } from '../lib/money'

export default function Home() {
  const [accounts, setAccounts] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .listAccounts()
      .then((data) => setAccounts(data.accounts))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Loading...</p>
  if (error) return <p className="error">{error}</p>

  return (
    <div>
      <h1>Your accounts</h1>
      {accounts.length === 0 ? (
        <p>
          You do not have an account yet. <Link to="/accounts/new">Open one</Link>.
        </p>
      ) : (
        <ul className="account-list">
          {accounts.map((account) => (
            <li key={account.accountId} className="card">
              <Link to={`/accounts/${account.accountId}`}>
                <strong>{account.accountType}</strong> #{account.accountId}
              </Link>
              {/* Divide by 100 to display, never to calculate. */}
              <span className="balance">{formatCents(account.balance)}</span>
              {account.status === 'FROZEN' && <span className="badge">FROZEN</span>}
            </li>
          ))}
        </ul>
      )}
      <p>
        <Link to="/accounts/new">Open account</Link> · <Link to="/transfer">Transfer</Link>
      </p>
    </div>
  )
}
