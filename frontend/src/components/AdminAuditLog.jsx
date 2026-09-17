/* Who did what, to which account, and why.
 *
 * Read-only, and that is the design rather than a missing feature: every freeze,
 * unfreeze and adjustment appends one row and nothing anywhere removes one.
 *
 * The entries carry no id and no timestamp, so they are rendered in the order
 * the server returned them, which is the order they happened - oldest first. */
export default function AdminAuditLog({ entries }) {
  if (entries.length === 0) {
    return <p className="hint">No admin action has been taken yet. Freeze or adjust an account and it appears here.</p>
  }

  return (
    <ul className="account-list">
      {entries.map((entry, index) => (
        <li key={index} className="card">
          <span>
            <strong>{entry.action}</strong> on account #{entry.accountId} by user #{entry.actorUserId}
            {' — '}
            {entry.reason}
          </span>
        </li>
      ))}
    </ul>
  )
}
