import { useParams } from 'react-router-dom'
/* Brief 7.6, reached from the nav. Pick an account, read its ledger.
 *
 * The table itself is Transactions.jsx, which is also the per-account page at
 * /accounts/:id/transactions. This page is the account picker in front of it. */
import { useState } from 'react'
import { useAuth } from '../context/auth-context'
import AccountPicker from '../components/AccountPicker'
import Transactions from './Transactions'
import NoAccountsYet from '../components/NoAccountsYet'

export default function History() {
  const { accounts } = useAuth()
  /* The account from the URL when there is one - /accounts/25/withdraw means
   * that account, and starting on a different one is how you withdraw from the
   * wrong place. Falls back to the first account for the bare /withdraw route. */
  const { accountId } = useParams()
  const [id, setId] = useState(Number(accountId) || accounts[0]?.accountId || '')

  if (accounts.length === 0) return <NoAccountsYet action="see the history of" />

  return (
    <div>
      <div className="card profile">
        <h1>History</h1>
        <AccountPicker accounts={accounts} value={id} onChange={setId} label="History for" />
      </div>
      {/* Transactions reads the id from the URL when it is the page at
          /accounts/:id/transactions, and from this prop when it is embedded. */}
      <Transactions accountId={id} />
    </div>
  )
}
