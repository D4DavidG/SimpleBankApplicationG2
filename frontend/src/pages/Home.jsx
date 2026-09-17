/* The home page, and the first thing anyone sees.
 *
 * It is public, so it has to be two pages in one: a landing page with the
 * sign-in form for a visitor, the account summary for somebody already signed
 * in. That is one `if`, and it is the reason every other route can stay behind
 * the auth guard - this is the only door.
 *
 * The offer shows either way. The only thing signing in removes is the sign-in
 * form beside it.
 */
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'
import { formatCents } from '../lib/money'
import LoginForm from '../components/LoginForm'
import AboutUs from '../components/AboutUs'

function Promo() {
  return (
    <div className="promo card lift">
      <h2>Start our new credit card with 10% APR!</h2>
      <div className="promo-inner card">
        <p>Start a new account at Simple Bank!</p>
        <p>Representative APR 10%. Credit is subject to status.</p>
        <Link className="apply lift" to="/register">Apply now</Link>
      </div>
    </div>
  )
}

/* One bar per account, each a different colour. The colour is picked by
 * accountId rather than by position in the list, so an account keeps the same
 * colour after one above it is closed or the order changes - a balance that
 * changes colour between visits is a balance you look at twice. */
function AccountBars({ accounts }) {
  return (
    <ul className="bars">
      {accounts.map((account) => (
        <li key={account.accountId}>
          <Link to={`/accounts/${account.accountId}`}
                className={`bar lift bar-${account.accountId % 6}`}>
            <span className="bar-type">{account.accountType}</span>
            {account.status === 'FROZEN' && <span className="badge">FROZEN</span>}
            {/* Divide by 100 to display, never to calculate. */}
            <span className="bar-balance">{formatCents(account.balance)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function Landing() {
  const navigate = useNavigate()
  return (
    <>
      <div className="hero">
        <Promo />
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

  return (
    <div>
      <h1>Welcome back, {user.name}</h1>

      {/* Same offer as the landing page, without the sign-in form beside it.
          Not shown to an admin: it is a customer acquisition offer, and an
          admin cannot open the account it is offering. */}
      {!isAdmin && (
        <div className="hero hero-solo">
          <Promo />
        </div>
      )}

      {/* An admin holds no accounts by design, so the customer empty state -
          "you do not have a bank account yet" - would read as something missing
          rather than something deliberate. */}
      {isAdmin ? (
        <div className="card">
          <p>
            Staff account. Admins do not hold accounts here: the role is to freeze
            accounts, correct balances, and read the record of both.
          </p>
        </div>
      ) : accounts.length > 0 ? (
        <AccountBars accounts={accounts} />
      ) : (
        <div className="card"><p>You do not have a bank account yet.</p></div>
      )}

      <div className="actions">
        {!isAdmin && <Link className="action lift" to="/accounts/new">Open an account</Link>}
        {accounts.length > 0 && <Link className="action lift" to="/transfer">Transfer money</Link>}
        <Link className="action lift" to="/profile">My details</Link>
        {isAdmin && <Link className="action lift" to="/admin">Admin tools</Link>}
      </div>

      {/* Not on a staff dashboard: it is a public-facing panel, and its navy
          button sits badly on the red admin theme. */}
      {!isAdmin && <AboutUs />}
    </div>
  )
}

export default function Home() {
  const { user } = useAuth()
  return user ? <Dashboard /> : <Landing />
}
