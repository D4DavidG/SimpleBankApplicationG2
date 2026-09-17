/* Brief 7.6. A table: transaction id, type, amount, date.
 *
 * TODO
 *   - api.listTransactions(accountId, { page, pageSize })
 *   - the response is an envelope: { items, page, pageSize, total, totalPages }
 *   - one row per item: txnId, type, formatCents(amount), formatDate(createdAt)
 *   - signedAmount is there if you want to colour credits and debits
 *   - prev/next buttons driven by totalPages
 */
import { useParams } from 'react-router-dom'
import Stub from '../components/Stub'

export default function Transactions() {
  const { accountId } = useParams()
  return (
    <Stub title={`Transactions for #${accountId}`}>
      <p><code>api.listTransactions({accountId}, {'{ page, pageSize }'})</code></p>
    </Stub>
  )
}
