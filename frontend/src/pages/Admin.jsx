/* Admin-only. Reachable only with a token whose user has role ADMIN; the
 * backend rejects every call here otherwise, whatever the UI shows.
 *
 * TODO - probably more than one page in the end:
 *   - api.adminUsers() / api.adminAccounts()
 *   - api.adminFreeze(accountId, frozen, reason)  reason >= 10 characters
 *   - api.adminAdjust(accountId, amount, direction, reason)  CREDIT or DEBIT
 *   - api.adminAudit()
 *   - api.adminReconciliation() -> { balanced, checked, discrepancies } — this is
 *     the one to have open during the demo; it should always read balanced: true
 */
import Stub from '../components/Stub'

export default function Admin() {
  return (
    <Stub title="Admin">
      <p>Users, accounts, freeze/unfreeze, adjustments, audit log, reconciliation.</p>
    </Stub>
  )
}
