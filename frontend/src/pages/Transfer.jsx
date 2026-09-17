/* Not in the brief's screen list; it is on the bonus list and the API supports it.
 *
 * TODO
 *   - pick a source account from api.listAccounts(), type a destination id
 *   - api.transfer(fromAccountId, toAccountId, cents, crypto.randomUUID())
 *   - you must own the source; you do not have to own the destination
 */
import Stub from '../components/Stub'

export default function Transfer() {
  return (
    <Stub title="Transfer">
      <p><code>api.transfer(fromAccountId, toAccountId, amountInCents, clientTxnId)</code></p>
    </Stub>
  )
}
