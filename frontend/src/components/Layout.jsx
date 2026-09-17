/* The frame every page renders inside: nav bar at the top, page below. */
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function Layout() {
  const { user, accounts, logout, isAdmin } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="app">
      <header className="nav">
        <Link to="/" className="nav-brand">Simple Bank</Link>
        {user && (
          <nav className="nav-links">
            <NavLink to="/">Home</NavLink>
            {/* Only worth a tab once there is something behind it. A new user
                sees "Open account" until they have one. */}
            {accounts.length > 0
              ? <NavLink to="/accounts">Accounts ({accounts.length})</NavLink>
              : <NavLink to="/accounts/new">Open account</NavLink>}
            <NavLink to="/transfer">Transfer</NavLink>
            {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          </nav>
        )}
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
            <NavLink to="/login">Log in</NavLink>
          )}
        </div>
      </header>

      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
