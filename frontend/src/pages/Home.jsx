/* The home page, and the first thing anyone sees.
 *
 * It is public, so it has to be two pages in one: a landing page with the sign-in
 * form for a visitor, and the account summary for somebody already signed in.
 * That is one `if`, and it is the reason every other route can stay behind the
 * auth guard - this is the only door.
 */
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'
import { formatCents } from '../lib/money'
import LoginForm from '../components/LoginForm'
import AboutUs from '../components/AboutUs'

function Landing() {
  const navigate = useNavigate()

  return (
    <>
      <div className="hero">
        <div className="promo card lift">
          <h2>Start our new credit card with 10% APR!</h2>
          <div className="promo-inner card">
            <p>Start a new account at Simple Bank!</p>
            <p>Representative APR 10%. Credit is subject to status.</p>
            <Link className="apply lift" to="/register">Apply now</Link>
          </div>
        </div>

        <div className="signin card">
          <LoginForm onDone={() => navigate('/')} />
        </div>
      </div>

      <AboutUs />
    </>
  )
}

function Dashboard() {
  const { user, accounts, isAdmin } = useAuth()

  // Summing cents, never dollars. Integers stay exact; the divide by 100 happens
  // once, inside formatCents, on the way to the screen.
  const total = accounts.reduce((sum, account) => sum + account.balance, 0)

  return (
    <div>
      <h1>Welcome back, {user.name}</h1>

      <div className="card">
        {accounts.length > 0 ? (
          <>
            <p className="hint">
              Across {accounts.length} account{accounts.length === 1 ? '' : 's'}
            </p>
            <p className="total">{formatCents(total)}</p>
          </>
        ) : (
          <p>You do not have a bank account yet.</p>
        )}
      </div>

      <div className="actions">
        {accounts.length > 0 && <Link className="action lift" to="/accounts">View accounts</Link>}
        <Link className="action lift" to="/accounts/new">Open an account</Link>
        {accounts.length > 0 && <Link className="action lift" to="/transfer">Transfer money</Link>}
        <Link className="action lift" to="/profile">My details</Link>
        {isAdmin && <Link className="action lift" to="/admin">Admin tools</Link>}
      </div>

      <AboutUs />
    </div>
  )
}

export default function Home() {
  const { user } = useAuth()
  return user ? <Dashboard /> : <Landing />
}
