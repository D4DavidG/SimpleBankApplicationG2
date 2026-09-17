/* Brief 7.5. One amount input, one submit button.
 *
 * TODO
 *   - parseDollars(input) -> cents
 *   - api.withdraw(accountId, cents, crypto.randomUUID())
 *   - the backend checks against availableForWithdrawal, so check the same
 *     field client-side rather than balance
 *   - "insufficient funds" and "account is frozen" come back as ApiError.message
 */
import { useParams } from 'react-router-dom'
import Stub from '../components/Stub'

export default function Withdraw() {
  const { accountId } = useParams()
  return (
    <Stub title={`Withdraw from #${accountId}`}>
      <p><code>api.withdraw(accountId, amountInCents, clientTxnId)</code></p>
    </Stub>
  )
}
