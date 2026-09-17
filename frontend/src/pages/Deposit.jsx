/* Brief 7.4. One amount input, one submit button.
 *
 * TODO
 *   - parseDollars(input) -> cents; refuse null before sending
 *   - api.deposit(accountId, cents, crypto.randomUUID())
 *   - show the returned account.balance - do not add the amount to the number
 *     you were already holding, that is the frontend doing money arithmetic
 */
import { useParams } from 'react-router-dom'
import Stub from '../components/Stub'

export default function Deposit() {
  const { accountId } = useParams()
  return (
    <Stub title={`Deposit into #${accountId}`}>
      <p><code>api.deposit(accountId, amountInCents, clientTxnId)</code></p>
    </Stub>
  )
}
