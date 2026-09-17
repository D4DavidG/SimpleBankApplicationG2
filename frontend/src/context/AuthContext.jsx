/* Who is logged in, for the whole app.
 *
 * On load this asks the backend whether the stored token is still good, rather
 * than assuming it is and letting the first real call fail. Until that answer
 * comes back `loading` is true and the router shows nothing, so a logged-in user
 * refreshing a page is never bounced to the login screen for a moment.
 */
import { useEffect, useState } from 'react'
import * as api from '../lib/api'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // With no stored token there is nothing to check, so the app is ready at once
  // and the "checking" state never appears. Read once: a token arriving later
  // comes from login() below, which sets the user itself.
  const [loading, setLoading] = useState(() => Boolean(api.getToken()))

  useEffect(() => {
    if (!api.getToken()) return
    api
      .me()
      .then((data) => setUser(data.user))
      .catch(() => api.setToken(null)) // expired or invalid: start logged out
      .finally(() => setLoading(false))
  }, [])

  async function login(email, password) {
    const data = await api.login(email, password)
    api.setToken(data.token)
    setUser(data.user)
    return data.user
  }

  async function register(name, email, password) {
    const data = await api.register(name, email, password)
    api.setToken(data.token) // register logs you straight in
    setUser(data.user)
    return data.user
  }

  function logout() {
    api.setToken(null)
    setUser(null)
  }

  const value = { user, loading, login, register, logout, isAdmin: user?.role === 'ADMIN' }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
