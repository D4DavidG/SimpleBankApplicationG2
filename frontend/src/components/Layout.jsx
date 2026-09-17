/* The frame every page renders inside: nav bar at the top, page below.
 *
 * Whoever takes the design pass owns this file and src/index.css. */
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function Layout() {
  const { user, logout, isAdmin } = useAuth()
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
            <NavLink to="/accounts/new">Open account</NavLink>
            <NavLink to="/transfer">Transfer</NavLink>
            {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          </nav>
        )}
        <div className="nav-user">
          {user ? (
            <>
              <span>{user.name}</span>
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
