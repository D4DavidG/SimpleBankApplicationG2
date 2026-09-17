/* Who is logged in, and which accounts they have, for the whole app.
 *
 * On load this asks the backend whether the stored token is still good, rather
 * than assuming it is and letting the first real call fail. Until that answer
 * comes back `loading` is true and the router shows nothing, so a logged-in user
 * refreshing a page is never bounced to the login screen for a moment.
 *
 * The account list lives here rather than in a page because two separate things
 * need it: the nav bar, to decide whether to show the Accounts tab, and the home
 * page, to list them. Fetching it in both would mean two calls on every load and
 * two versions of the truth.
 *
 * IMPORTANT for whoever builds deposit, withdraw and transfer: those change a
 * balance, so call `refreshAccounts()` after a successful one or the nav and the
 * home page will keep showing the old number.
 */
import { useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [accounts, setAccounts] = useState([])
  // With no stored token there is nothing to check, so the app is ready at once
  // and the "checking" state never appears.
  const [loading, setLoading] = useState(() => Boolean(api.getToken()))

  const refreshAccounts = useCallback(async () => {
    const data = await api.listAccounts()
    setAccounts(data.accounts)
    return data.accounts
  }, [])

  useEffect(() => {
    if (!api.getToken()) return
    api
      .me()
      .then((data) => {
        setUser(data.user)
        return refreshAccounts()
      })
      .catch(() => api.setToken(null)) // expired or invalid: start logged out
      .finally(() => setLoading(false))
  }, [refreshAccounts])

  async function login(email, password) {
    const data = await api.login(email, password)
    api.setToken(data.token)
    setUser(data.user)
    await refreshAccounts()
    return data.user
  }

  // adminCode is optional and only the admin register page sends one. The server
  // decides the role; whatever comes back in data.user.role is the real answer.
  async function register(name, email, password, adminCode) {
    const data = await api.register(name, email, password, adminCode)
    api.setToken(data.token) // register logs you straight in
    setUser(data.user)
    setAccounts([]) // a brand new user has none yet
    return data.user
  }

  async function updateProfile(changes) {
    const data = await api.updateProfile(changes)
    setUser(data.user)
    return data.user
  }

  function logout() {
    api.setToken(null)
    setUser(null)
    setAccounts([])
  }

  const value = {
    user, accounts, loading,
    login, register, logout, updateProfile, refreshAccounts,
    isAdmin: user?.role === 'ADMIN',
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
