/* Brief 7.3. Displays account id, owner name and balance; links to deposit,
 * withdraw and transactions.
 *
 * TODO
 *   - api.getAccount(accountId) -> { account }
 *   - show accountId, userName, formatCents(account.balance), status
 *   - offer availableForWithdrawal, not balance, as the withdrawable figure
 *   - buttons through to ./deposit, ./withdraw, ./transactions
 */
import { useParams } from 'react-router-dom'
import Stub from '../components/Stub'

export default function AccountDetails() {
  const { accountId } = useParams()
  return (
    <Stub title={`Account #${accountId}`}>
      <p><code>api.getAccount({accountId})</code></p>
    </Stub>
  )
}
