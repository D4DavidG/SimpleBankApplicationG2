import { Link, useNavigate } from 'react-router-dom'
import LoginForm from '../components/LoginForm'

export default function Login() {
  const navigate = useNavigate()
  return (
    <div className="card narrow">
      <h1>Sign in</h1>
      <LoginForm onDone={() => navigate('/')} />
      {/* TEMPORARY test hook, not mine - kept because the public /transactions
        * route it points at is still there, and the two are meant to be deleted
        * together once a real caller for TransactionMenu exists. */}
      <p><Link to="/transactions">Transaction menu (test)</Link></p>
      <p className="hint">
        Seed login: <code>aaron.forrester@example.com</code>, password
        <code>BankDemo123!</code>.
      </p>
    </div>
  )
}
