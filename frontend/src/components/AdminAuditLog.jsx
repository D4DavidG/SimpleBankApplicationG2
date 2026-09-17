/* Who did what, to which account, and why.
 *
 * Read-only, and that is the design rather than a missing feature: every freeze,
 * unfreeze and adjustment appends one row and nothing anywhere removes one.
 *
 * Newest first. The server returns them oldest first, which is the right order
 * for a ledger and the wrong one for a column you are watching - after an
 * action you want to see it without scrolling. The entries carry no id and no
 * timestamp, so position is the only ordering there is. */
export default function AdminAuditLog({ entries }) {
  if (entries.length === 0) {
    return <p className="hint">Nothing yet. Freeze or adjust an account and it appears here.</p>
  }

  return (
    <ol className="admin-log">
      {entries
        .slice()
        .reverse()
        .map((entry, index) => (
          <li key={entries.length - index}>
            <span className="admin-log-action">{entry.action}</span>
            <span className="admin-log-where">
              account #{entry.accountId} · by user #{entry.actorUserId}
            </span>
            <span>{entry.reason}</span>
          </li>
        ))}
    </ol>
  )
}
