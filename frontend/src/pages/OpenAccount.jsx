/* Brief 7.2 (the bank-account half). Fields: account type, opening balance.
 *
 * TODO
 *   - a select with CHECKING and SAVINGS
 *   - an optional opening balance, run through parseDollars() to get cents
 *   - api.openAccount(accountType, openingBalanceCents)
 *   - on success, navigate to /accounts/{result.account.accountId}
 * The owner comes from the token, so there is no user field to fill in.
 */
import Stub from '../components/Stub'

export default function OpenAccount() {
  return (
    <Stub title="Open account">
      <p>
        <code>api.openAccount(accountType, openingBalance)</code> — accountType is
        <code>'CHECKING'</code> or <code>'SAVINGS'</code>; openingBalance is cents and
        defaults to 0. A non-zero opening balance is posted as a real DEPOSIT.
      </p>
    </Stub>
  )
}
