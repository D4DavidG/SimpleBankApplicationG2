/* Wraps the routes that need a token. An admin-only route adds admin.
 *
 * This is convenience, not security: the backend checks the token and the role
 * on every single request, and hiding a link has never stopped anybody. */
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function RequireAuth({ admin = false, children }) {
  const { user, loading, isAdmin } = useAuth()
  const location = useLocation()

  if (loading) return null // the "is my stored token still good" check is in flight
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (admin && !isAdmin) return <Navigate to="/" replace />
  return children
}
