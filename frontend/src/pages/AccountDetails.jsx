import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as api from '../lib/api'
import { formatCents } from '../lib/money'

export default function AccountDetails() {
  const { accountId } = useParams()
  const [account, setAccount] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!accountId) return

    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)

      try {
        const { account } = await api.getAccount(Number(accountId))
        if (!cancelled) setAccount(account)
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Unable to load this account.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [accountId])

  if (loading) {
    return (
      <div className="card">
        <h1>Account details</h1>
        <p className="hint">Loading account...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <h1>Account details</h1>
        <p className="error">{error}</p>
      </div>
    )
  }

  if (!account) {
    return (
      <div className="card">
        <h1>Account details</h1>
        <p>No account found.</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h1>{account.accountType} account #{account.accountId}</h1>

      <dl className="details">
        <dt>Owner</dt>
        <dd>{account.userName ?? 'Unknown owner'}</dd>

        <dt>Balance</dt>
        <dd className="balance">{formatCents(account.balance)}</dd>

        <dt>Type</dt>
        <dd>{account.accountType}</dd>

        <dt>Available to withdraw</dt>
        <dd>{formatCents(account.availableForWithdrawal)}</dd>

        <dt>Status</dt>
        <dd>{account.status === 'FROZEN' ? <span className="badge">FROZEN</span> : account.status}</dd>
      </dl>

      <div className="actions">
        <Link className="action" to={`/accounts/${account.accountId}/deposit`}>Deposit</Link>
        <Link className="action" to={`/accounts/${account.accountId}/withdraw`}>Withdraw</Link>
        <Link className="action" to={`/accounts/${account.accountId}/transactions`}>Transactions</Link>
      </div>
    </div>
  )
}
