/* Who did what, to which account, why, and when.
 *
 * Read-only, and that is the design rather than a missing feature: every freeze,
 * unfreeze and adjustment appends one row and nothing anywhere removes one.
 * Every field here is persisted - in MongoDB it is a document in `audit_log`
 * carrying the same five values.
 *
 * Newest first. The server returns them oldest first, which is the right order
 * for a ledger and the wrong one for a column you are watching - after an
 * action you want to see it without scrolling. */

/* The server sends UTC; an admin in the office thinks in Eastern. Built once at
 * module level rather than per row, because constructing a DateTimeFormat is the
 * expensive part and there may be hundreds of rows.
 *
 * `America/New_York`, not a fixed -05:00: that is what makes the offset follow
 * daylight saving instead of being wrong for eight months of the year.
 * `timeZoneName` then prints EST or EDT, so the label is never a claim the
 * clock does not support. */
const EASTERN = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

function easternTime(iso) {
  if (!iso) return null
  const when = new Date(iso)
  return Number.isNaN(when.getTime()) ? null : EASTERN.format(when)
}

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
              {easternTime(entry.createdAt) ?? 'time not recorded'}
            </span>
            <span className="admin-log-where">
              account #{entry.accountId} · by user #{entry.actorUserId}
            </span>
            <span>{entry.reason}</span>
          </li>
        ))}
    </ol>
  )
}
