/* Every route in the app, in one table - the frontend's answer to the route
 * table in bank/api.py. Add a page here and in src/pages/, nowhere else. */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import RequireAuth from './components/RequireAuth'

import Login from './pages/Login'
import Register from './pages/Register'
import Home from './pages/Home'
import OpenAccount from './pages/OpenAccount'
import AccountDetails from './pages/AccountDetails'
import Deposit from './pages/Deposit'
import Withdraw from './pages/Withdraw'
import Transactions from './pages/Transactions'
import Transfer from './pages/Transfer'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'

// Wrapping each protected element rather than nesting a guard route keeps the
// list flat and lets you see at a glance which pages need a token.
const auth = (element) => <RequireAuth>{element}</RequireAuth>

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            {/* public */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* customer */}
            <Route path="/" element={auth(<Home />)} />
            <Route path="/accounts/new" element={auth(<OpenAccount />)} />
            <Route path="/accounts/:accountId" element={auth(<AccountDetails />)} />
            <Route path="/accounts/:accountId/deposit" element={auth(<Deposit />)} />
            <Route path="/accounts/:accountId/withdraw" element={auth(<Withdraw />)} />
            <Route path="/accounts/:accountId/transactions" element={auth(<Transactions />)} />
            <Route path="/transfer" element={auth(<Transfer />)} />

            {/* admin */}
            <Route path="/admin" element={<RequireAuth admin><Admin /></RequireAuth>} />

            <Route path="/home" element={<Navigate to="/" replace />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
