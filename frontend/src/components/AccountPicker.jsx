/* "Which account?" - the first question on Deposit, Withdraw and History.
 *
 * With one account there is no question, so it is not asked: the picker renders
 * as a plain label instead of a one-option dropdown that cannot be changed. */
import { accountLabel, accountTone } from '../lib/accounts'
import { formatCents } from '../lib/money'

export default function AccountPicker({ accounts, value, onChange, label = 'Account' }) {
  const current = accounts.find((a) => a.accountId === Number(value))

  if (accounts.length === 1) {
    return (
      <div className={`picked-account tone-${accountTone(accounts[0])}`}>
        <strong>{accountLabel(accounts[0])}</strong>
        <span className="balance">{formatCents(accounts[0].balance)}</span>
      </div>
    )
  }

  return (
    <>
      <label>
        {label}
        <select value={value} onChange={(e) => onChange(Number(e.target.value))}>
          {accounts.map((a) => (
            <option key={a.accountId} value={a.accountId}>
              {accountLabel(a)} — {formatCents(a.balance)}
            </option>
          ))}
        </select>
      </label>
      {/* A stripe in the account's own colour, so the dropdown is not the only
          thing saying which one is selected. */}
      {current && <div className={`picked-strip tone-${accountTone(current)}`} />}
    </>
  )
}
