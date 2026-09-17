/* How an account is named and coloured. One place, because the home page, the
 * accounts list, the detail page and every picker all have to agree - an
 * account that is teal in one list and violet in another is worse than one
 * with no colour at all.
 */

/** "Checking...23" - the type, then the number that tells two of them apart. */
export function accountLabel(account) {
  const type = account.accountType.charAt(0) + account.accountType.slice(1).toLowerCase()
  return `${type}...${account.accountId}`
}

/**
 * The colour class suffix. Credit always looks the same, because it is a
 * different product rather than another account of the same kind - that is the
 * whole point of it being recognisable. Everything else is picked by
 * accountId, so an account keeps its colour when another one is closed.
 */
export function accountTone(account) {
  return account.accountType === 'CREDIT' ? 'credit' : String(account.accountId % 6)
}

export const isCredit = (account) => account.accountType === 'CREDIT'
