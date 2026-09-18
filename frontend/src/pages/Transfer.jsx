/* Send money to somebody. Pick the person by name, not by account number.
 *
 * The destination goes to the server as a user id and the server resolves it to
 * that person's primary account, so this page never holds - and never has to be
 * told - anyone else's account ids.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'
import * as api from '../lib/api'
import { formatCents, parseDollars } from '../lib/money'
import { accountLabel } from '../lib/accounts'
import UserSearch from '../components/UserSearch'

export default function Transfer() {
  const { accounts, refreshAccounts } = useAuth()
  const navigate = useNavigate()
  const [fromId, setFromId] = useState(accounts[0]?.accountId ?? '')
  const [person, setPerson] = useState(null)
  const [amount, setAmount] = useState('')
  const [error, setError] = useState(null)
  const [done, setDone] = useState(null)
  const [busy, setBusy] = useState(false)

  const from = accounts.find((a) => a.accountId === Number(fromId))

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    // Same rule the server applies, stated here so the message comes from the
    // field rather than from a failed request.
    const cents = parseDollars(amount)
    if (cents === null) {
      setError('Enter an amount like 25 or 25.00.')
      return
    }
    if (from && cents > from.availableForWithdrawal) {
      setError(`That is more than the ${formatCents(from.availableForWithdrawal)} available.`)
      return
    }

    setBusy(true)
    try {
      // One id per submission attempt, so a double-click cannot send twice.
      const result = await api.transferToUser(
        Number(fromId), person.userId, cents, crypto.randomUUID(),
      )
      // The nav bar and the home page read the account list, so it has to be
      // refreshed or both keep showing the old balance.
      await refreshAccounts()
      // Show the balance the server returned. Never the one we were holding.
      setDone(`Sent ${formatCents(cents)} to ${person.name}. ` +
              `New balance: ${formatCents(result.account.balance)}.`)
      setPerson(null)
      setAmount('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (accounts.length === 0) {
    return (
      <div className="card narrow">
        <h1>Transfer</h1>
        <p>You need an account before you can send money.</p>
        <button onClick={() => navigate('/accounts/new')}>Open an account</button>
      </div>
    )
  }

  return (
    <div className="card profile">
      <h1>Send money</h1>
      <form onSubmit={handleSubmit}>
        <label>
          From
          <select value={fromId} onChange={(e) => setFromId(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.accountId} value={a.accountId}>
                {accountLabel(a)} — {formatCents(a.balance)}
              </option>
            ))}
          </select>
        </label>

        <UserSearch selected={person} onSelect={setPerson} />

        <label>
          Amount
          <input value={amount} onChange={(e) => setAmount(e.target.value)}
                 inputMode="decimal" placeholder="25.00" />
        </label>

        {error && <p className="error">{error}</p>}
        {done && <p className="success">{done}</p>}

        <button type="submit" className="lift" disabled={busy || !person}>
          {busy ? 'Sending...' : 'Send money'}
        </button>
        {!person && <p className="hint">Choose who to send to first.</p>}
      </form>
    </div>
  )
}
