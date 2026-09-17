/* The admin console: what an ADMIN may do that a customer may not, which is
 * freeze an account, correct a balance, and read the record of both.
 *
 * An admin holds no accounts of their own - the rule is in
 * BankService.open_account - so there is nothing here about opening one or
 * moving money the ordinary way. Everything on this page is done TO somebody
 * else's account, which is why every action needs a written reason and lands in
 * the log on the left.
 *
 * RequireAuth keeps a customer off this route, but that is convenience and not
 * security: the backend checks the role on every one of these calls and refuses
 * them whatever this page happens to render.
 *
 * Deliberately not here: GET /api/admin/users. It is a table of names that
 * demonstrates nothing the account list does not. */
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/auth-context'
import * as api from '../lib/api'
import AdminAccountRow from '../components/AdminAccountRow'
import AdminAuditLog from '../components/AdminAuditLog'
import './Admin.css'

/* One account against the search box and the type filter.
 *
 * The name match is case-insensitive and matches anywhere, so "for" finds
 * Aaron Forrester. A query that is all digits also matches the account id,
 * because an admin arriving from the audit log has an id in hand rather than a
 * name - the log records what was done to #12, not to Justin. */
function matches(account, query, kind) {
  if (kind !== 'ALL' && account.accountType !== kind) return false
  const q = query.trim().toLowerCase()
  if (q === '') return true
  return account.userName.toLowerCase().includes(q) || String(account.accountId) === q
}

export default function Admin() {
  const { refreshAccounts } = useAuth()
  const [accounts, setAccounts] = useState([])
  const [entries, setEntries] = useState([])
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('ALL')

  /* One reload for all of it, because any admin action moves all of it: the
   * account's balance or status, the audit row that recorded it, and the
   * reconciliation that counts it. Refreshing only the row that changed would
   * leave the other two quietly stale, and a stale reconciliation is worse than
   * none - it is a correctness claim about numbers it has not re-read. */
  const load = useCallback(
    () =>
      Promise.all([api.adminAccounts(), api.adminAudit(), api.adminReconciliation(), refreshAccounts()])
        .then(([accountList, audit, reconciliation]) => {
          setAccounts(accountList.accounts)
          setEntries(audit.entries)
          setReport(reconciliation)
          setError(null)
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false)),
    [refreshAccounts],
  )

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <p>Loading...</p>
  if (error) return <p className="error">{error}</p>

  const visible = accounts.filter((account) => matches(account, query, kind))

  return (
    <div className="admin theme-admin">
      <h1>Admin</h1>

      {/* The running proof that no code path has changed a balance without
        * writing a matching ledger entry. It should read balanced on every
        * refresh; the day it does not, this is the first thing to look at.
        * The state is in the words, not only in the colour. */}
      {report && (
        <p className={report.balanced ? 'admin-reconciliation hint' : 'admin-reconciliation error'}>
          {report.balanced
            ? `Balanced — ${report.checked} accounts checked, every balance matches its ledger.`
            : `Not balanced — ${report.discrepancies.length} of ${report.checked} accounts disagree with their ledger.`}
        </p>
      )}

      <div className="admin-layout">
        <section>
          <h2>Audit log</h2>
          <AdminAuditLog entries={entries} />
        </section>

        <section>
          <h2>Accounts</h2>
          <div className="admin-filters">
            <label>
              Search by name or id
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Aaron, or 12"
              />
            </label>
            <label>
              Type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="ALL">All</option>
                <option value="CHECKING">Checking</option>
                <option value="SAVINGS">Savings</option>
              </select>
            </label>
          </div>
          <p className="hint">
            Showing {visible.length} of {accounts.length} accounts.
          </p>
          {visible.length === 0 ? (
            <p>Nothing matches that search.</p>
          ) : (
            visible.map((account) => (
              <AdminAccountRow key={account.accountId} account={account} onChanged={load} />
            ))
          )}
        </section>
      </div>
    </div>
  )
}
