/* The admin console: what an ADMIN may do that a customer may not.
 *
 * RequireAuth keeps a customer off this route, but that is convenience and not
 * security - the backend checks the role on every one of these six calls and
 * refuses them whatever this page happens to render. Hiding a link has never
 * stopped anybody.
 *
 * Deliberately not here: GET /api/admin/users. It is a table of names that
 * demonstrates nothing the account list does not, and this page is already the
 * largest in the app. */
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/auth-context'
import * as api from '../lib/api'
import AdminAccountRow from '../components/AdminAccountRow'
import AdminAuditLog from '../components/AdminAuditLog'
import './Admin.css'

export default function Admin() {
  const { refreshAccounts } = useAuth()
  const [accounts, setAccounts] = useState([])
  const [entries, setEntries] = useState([])
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  /* One reload for all three, because any admin action moves all three: the
   * account's balance or status, the audit row that recorded it, and the
   * reconciliation that counts it. Refreshing only the row that changed would
   * leave the other two quietly stale, and a stale reconciliation is worse than
   * none - it is a correctness claim about numbers it has not re-read.
   *
   * refreshAccounts is in there because an admin has accounts of their own and
   * may well freeze or adjust one; without it the nav and the home page would
   * keep showing the balance from before their own correction. */
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

  return (
    <div className="admin theme-admin">
      <h1>Admin</h1>

      {/* The running proof that no code path has changed a balance without
        * writing a matching ledger entry. It should read balanced on every
        * refresh; the day it does not, this is the first thing to look at.
        * The state is in the words, not only in the colour. */}
      {report && (
        <p className={report.balanced ? 'hint' : 'error'}>
          {report.balanced
            ? `Balanced — ${report.checked} accounts checked, every balance matches its ledger.`
            : `Not balanced — ${report.discrepancies.length} of ${report.checked} accounts disagree with their ledger.`}
        </p>
      )}

      <h2>Accounts</h2>
      {accounts.map((account) => (
        <AdminAccountRow key={account.accountId} account={account} onChanged={load} />
      ))}

      <h2>Audit log</h2>
      <AdminAuditLog entries={entries} />
    </div>
  )
}
