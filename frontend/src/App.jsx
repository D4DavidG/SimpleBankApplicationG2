/* Every route in the app, in one table - the frontend's answer to the route
 * table in bank/api.py. Add a page here and in src/pages/, nowhere else. */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import RequireAuth from './components/RequireAuth'

import Login from './pages/Login'
import Register from './pages/Register'
import AdminLogin from './pages/AdminLogin'
import AdminRegister from './pages/AdminRegister'
import Home from './pages/Home'
import Accounts from './pages/Accounts'
import Profile from './pages/Profile'
import OpenAccount from './pages/OpenAccount'
import AccountDetails from './pages/AccountDetails'
import Deposit from './pages/Deposit'
import Withdraw from './pages/Withdraw'
import Transactions from './pages/Transactions'
import TransactionMenu from './pages/TransactionMenu'
import Transfer from './pages/Transfer'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'

// Wrapping each protected element rather than nesting a guard route keeps the
// list flat and lets you see at a glance which pages need a token.
const auth = (element) => <RequireAuth>{element}</RequireAuth>

// TEMPORARY: stand-in for the account the real caller will pass to
// TransactionMenu. Same shape as an item from api.listAccounts(), balance in
// cents. Delete with the /transactions route below.
const DEMO_ACCOUNT = {
  accountId: 1,
  accountType: 'CHECKING',
  balance: 125000,
  status: 'ACTIVE',
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            {/* public */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            {/* The staff door. Public, like any login page - what makes somebody
                an admin is the role on their account, which the server checks on
                every admin request. Hiding a URL has never stopped anybody. */}
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin/register" element={<AdminRegister />} />

            {/* TEMPORARY: public, with a made-up account, so the test link on
              * /login can reach it. TransactionMenu takes its account as a
              * prop; the real caller will pass one it fetched. Delete this
              * route and DEMO_ACCOUNT once that caller exists. */}
            <Route path="/transactions" element={<TransactionMenu account={DEMO_ACCOUNT} />} />

            {/* customer */}
            <Route path="/" element={auth(<Home />)} />
            <Route path="/profile" element={auth(<Profile />)} />
            <Route path="/accounts" element={auth(<Accounts />)} />
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
