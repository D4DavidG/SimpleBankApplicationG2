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

  /* Same colour this account wears on the home page, so arriving here from a
   * bar is obviously the same account. Picked by accountId, not by position, so
   * it does not change when another account is closed. */
  const tint = `tint-${account.accountId % 6}`

  return (
    <div className={`card profile ${tint}`}>
      <div className="profile-head">
        {/* No account number. The type and the owner are what a person
            recognises; the id is a database key and stays in the URL. */}
        <h1>{account.accountType} account</h1>
        {account.status === 'FROZEN' && <span className="badge">FROZEN</span>}
      </div>

      <dl className="detail-rows">
        <div><dt>Owner</dt><dd>{account.userName ?? 'Unknown owner'}</dd></div>
        <div><dt>Balance</dt><dd>{formatCents(account.balance)}</dd></div>
        <div><dt>Type</dt><dd>{account.accountType}</dd></div>
        <div>
          <dt>Available to withdraw</dt>
          <dd>{formatCents(account.availableForWithdrawal)}</dd>
        </div>
        <div><dt>Status</dt><dd>{account.status}</dd></div>
      </dl>

      <div className="actions">
        <Link className="action lift" to={`/accounts/${account.accountId}/deposit`}>Deposit</Link>
        <Link className="action lift" to={`/accounts/${account.accountId}/withdraw`}>Withdraw</Link>
        <Link className="action lift" to={`/accounts/${account.accountId}/transactions`}>Transactions</Link>
      </div>
    </div>
  )
}
