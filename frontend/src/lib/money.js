/* Money is an integer number of cents everywhere except on screen.
 *
 * 123456 is 1,234.56. The backend refuses fractional numbers and strings
 * outright, so the only safe move is to keep cents in state and convert at the
 * edges: `formatCents` on the way to the screen, `parseDollars` on the way in
 * from an input. Never add, subtract or compare dollar values - do that in
 * cents, and never re-derive a balance in the browser. Every write endpoint
 * returns the new authoritative account; display that.
 */

/** 123456 -> "$1,234.56" */
export function formatCents(cents) {
  return (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

/**
 * "1,234.56" -> 123456. Returns null if the text is not a usable amount, so a
 * caller can show a message instead of sending something the backend refuses.
 * Rounds rather than truncates, so "0.005" does not silently become 0.
 */
export function parseDollars(text) {
  const cleaned = String(text).trim().replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null
  const cents = Math.round(Number(cleaned) * 100)
  return cents > 0 ? cents : null
}

/** "2026-09-15T14:03:11.482913+00:00" -> "Sep 15, 2026, 2:03 PM" */
export function formatDate(iso) {
  return new Date(iso).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}
