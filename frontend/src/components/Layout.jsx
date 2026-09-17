/* The frame every page renders inside: nav bar at the top, page below. */
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function Layout() {
  const { user, accounts, logout, isAdmin } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  /* Red bar whenever anything admin is going on: you are signed in as an admin,
   * or you are standing on a staff page. `.theme-admin` redefines --navy, and
   * the bar is painted with --navy, so nothing below has to know about this. */
  const adminContext = isAdmin || location.pathname.startsWith('/admin')

  function handleLogout() {
    logout()
    navigate('/')
  }

  return (
    <div className="app">
      <header className={adminContext ? 'nav theme-admin' : 'nav'}>
        {/* The bar spans the window; this keeps its contents on the same rail as
            the page below, so the brand is not stuck to the window edge. */}
        <div className="nav-inner">
        <Link to="/" className="nav-brand">Simple Bank</Link>

        <nav className="nav-links">
          <NavLink to="/" end>Home</NavLink>
          {/* Only worth a tab once there is something behind it. A visitor and a
              new customer both see "Open account" instead. */}
          {accounts.length > 0
            ? <NavLink to="/accounts">Accounts ({accounts.length})</NavLink>
            : <NavLink to="/accounts/new">Open account</NavLink>}
          {user && <NavLink to="/transfer">Transfer</NavLink>}
          {isAdmin && <NavLink to="/admin">Admin</NavLink>}
        </nav>

        <div className="nav-user">
          {user ? (
            <>
              {/* The name is the way into the profile - the usual place to look. */}
              <NavLink to="/profile" className="nav-name">
                {user.name}
                {isAdmin && <span className="nav-role">ADMIN</span>}
              </NavLink>
              <button onClick={handleLogout}>Log out</button>
            </>
          ) : (
            <>
              <NavLink to="/register">Register</NavLink>
              <NavLink to="/login">Sign in</NavLink>
            </>
          )}
        </div>
        </div>
      </header>

      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
