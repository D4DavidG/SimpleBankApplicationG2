import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as api from '../lib/api'
import { formatCents, formatDate } from '../lib/money'

/* Used two ways: as the page at /accounts/:id/transactions, where the id comes
 * from the URL, and embedded in History.jsx, where it arrives as a prop. The
 * prop wins when it is there, so the same table serves both. */
export default function Transactions({ accountId: accountIdProp }) {
  const params = useParams()
  const accountId = accountIdProp ?? params.accountId
  const [page, setPage] = useState(1)
  const [pageSize] = useState(10)
  const [items, setItems] = useState([])
  const [totalPages, setTotalPages] = useState(1)
  const [currentBalance, setCurrentBalance] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!accountId) return

    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)

      try {
        const accountData = await api.getAccount(Number(accountId))
        const data = await api.listTransactions(Number(accountId), { page, pageSize })

        if (!cancelled) {
          setCurrentBalance(accountData.account.balance)
          setItems(data.items)
          setTotalPages(data.totalPages || 1)
        }
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Unable to load transactions.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [accountId, page, pageSize])

  const rows = useMemo(() => {
    if (currentBalance === null) return []

    let runningBalance = currentBalance
    return items.map((txn) => {
      const result = runningBalance
      runningBalance -= txn.signedAmount
      return { ...txn, resultingBalance: result }
    })
  }, [currentBalance, items])

  if (loading) {
    return (
      <div className="card">
        <h1>Transactions</h1>
        <p className="hint">Loading activity...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <h1>Transactions</h1>
        <p className="error">{error}</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h1>Transactions</h1>

      <p className="hint">
        Showing {items.length} result{items.length === 1 ? '' : 's'} on page {page}.
      </p>

      {items.length === 0 ? (
        <p>No transactions yet.</p>
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Resulting balance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((txn) => (
                <tr key={txn.txnId}>
                  <td>{formatDate(txn.createdAt)}</td>
                  <td>{txn.type}</td>
                  <td className={txn.signedAmount >= 0 ? 'credit' : 'debit'}>
                    {formatCents(txn.signedAmount)}
                  </td>
                  <td className="balance">{formatCents(txn.resultingBalance)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="row" style={{ justifyContent: 'space-between', marginTop: '1rem' }}>
            <button type="button" className="secondary" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              Previous
            </button>
            <span className="hint">Page {page} of {totalPages}</span>
            <button type="button" className="secondary" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
              Next
            </button>
          </div>
        </>
      )}

      <p style={{ marginTop: '1rem' }}>
        <Link to={`/accounts/${accountId}`}>Back to account</Link>
      </p>
    </div>
  )
}
