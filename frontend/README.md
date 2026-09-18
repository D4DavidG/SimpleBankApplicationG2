# Simple Bank Application: frontend

React + Vite. Plain JavaScript, plain CSS, no UI library. Routing,
authentication and the API layer work, and every screen in brief §7 is built.

```bash
npm install          # once
npm run dev          # http://localhost:5173
npm run build        # production bundle into dist/
npm run lint         # oxlint, currently clean - keep it that way
```

The backend has to be running too, in another terminal, from the repo root:

```bash
python server.py     # http://127.0.0.1:8000
```

`npm run dev` proxies `/api` to `127.0.0.1:8000` (see `vite.config.js`), so the
browser sees a single origin and there is nothing to configure. If you run the
backend on another port:

```bash
VITE_API_TARGET=http://127.0.0.1:9000 npm run dev          # bash
$env:VITE_API_TARGET = "http://127.0.0.1:9000"; npm run dev  # PowerShell
```

Log in with a seeded user: `aaron.forrester@example.com`, password
`BankDemo123!`. The seeded admins are `david.gusmao@example.com` and
`bianca.alvarado@example.com`, same password.

---

## What is already done

| File | What it is |
| --- | --- |
| `src/lib/api.js` | One function per endpoint. Handles the `Authorization` header, JSON encoding, the `{ error }` failure shape, and the session teardown on a 401. **Do not call `fetch` from a page.** |
| `src/lib/money.js` | `formatCents`, `parseDollars`, `formatDate`. |
| `src/context/AuthContext.jsx` | Login, register, logout, the stored token, the profile edit, the account list, and `sessionExpired`. |
| `src/context/auth-context.js` | The `useAuth()` hook. |
| `src/components/RequireAuth.jsx` | Route guard: redirects to `/login`, or away from `/admin` for a non-admin. |
| `src/components/Layout.jsx` | Nav bar and page frame. Turns red in admin context. |
| `src/components/SecretInput.jsx` | A hidden field with an eye to reveal it. Used for passwords and the team code. |
| `src/App.jsx` | Every route, in one table. |
| `src/index.css` | Placeholder styles. Nobody is attached to these. |

Every route in the table below is built and works against live data. Deposit,
withdraw and transfer all render the one shared money form, `TransactionMenu.jsx`
— see PLAN.md §2 before changing any of them, because the amount parsing, the
`clientTxnId` and the "render the balance the server returned" rule live there
once rather than three times.

### When the token stops working

Tokens are signed JWTs, so they are not stored anywhere and cannot be cancelled;
what ends a session is the expiry, or the backend restarting without
`BANK_SECRET` set, which changes the signing key and invalidates every token at
once. That second one happens constantly in development.

`request()` in `src/lib/api.js` handles it in one place: **any 401 clears the
stored token and drops the signed-in user**, so `RequireAuth` redirects to the
sign-in form and `LoginForm` explains why. Login and register are exempt — a 401
there means the password was wrong, not that a session ended.

Do not add 401 handling to a page. It is done once, and a page that catches it
separately will fight the redirect.

### Staff accounts

There is one login page and one register page, for everybody. Staff are not a
separate door — what makes somebody an admin is the role on their account, which
the server re-checks on every admin request.

The register form carries an optional **team code**. Leave it empty and you get
an ordinary customer account. Fill it in correctly and you get an admin one.

**The code is never checked in the browser.** It is sent to the server as
`adminCode` and compared against `BANK_ADMIN_CODE` from `.env`. Grep the built
bundle for the code and you will not find it, which is the whole point — a
comparison written in JavaScript ships to the browser and stops nobody.

A wrong code comes back as a 403 that creates no user at all, and the page then
asks whether an ordinary account was what you meant. Saying yes sends the request
again with no code in it; the rejected code is not stored, logged or resent. If
`BANK_ADMIN_CODE` is not set on the server, admin registration is closed and
every code is refused.

The nav bar turns red once an admin is signed in, so the context is never in
doubt.

## The pages

One page per file in `src/pages/`. All of these are built; the current table,
with what is still open, is in **[PLAN.md](PLAN.md)**.

| Route | File | Brief |
| --- | --- | --- |
| `/accounts/new` | `OpenAccount.jsx` | 7.2 |
| `/accounts/:accountId` | `AccountDetails.jsx` | 7.3 |
| `/deposit`, `/accounts/:accountId/deposit` | `Deposit.jsx` | 7.4 |
| `/withdraw`, `/accounts/:accountId/withdraw` | `Withdraw.jsx` | 7.5 |
| `/history`, `/accounts/:accountId/transactions` | `History.jsx`, `Transactions.jsx` | 7.6 |
| `/transfer` | `Transfer.jsx` | bonus |
| `/admin` | `Admin.jsx` | admin surface |

Adding a page means a file in `src/pages/` and a line in `src/App.jsx`. Nothing
else.

## Three rules that will bite you

**Money is an integer number of cents.** `123456` is `1,234.56`. The backend
refuses `25.00` and `"2500"` with a 400 rather than guessing, because guessing
wrong is a hundredfold error. Keep cents in state, use `formatCents` on the way
to the screen and `parseDollars` on the way in from an input, and never do
arithmetic on a dollar value.

**Never compute a balance in the browser.** Every write endpoint returns the new
authoritative `account` next to the transaction. Display that. Adding the amount
to the number you were already holding is wrong the moment a second tab is open.

**Send a `clientTxnId` on deposit, withdraw and transfer.** One
`crypto.randomUUID()` per submission attempt. A double-clicked button then sends
the same id twice and the second one is refused instead of moving the money
again.

**Call `refreshAccounts()` after moving money.** The account list lives in the
auth context because the nav bar and the home page both read it. Skip the
refresh and both keep showing the old balance.

Two more worth knowing: read `availableForWithdrawal`, not `balance`, when
offering an amount to withdraw — they hold the same number today and will not
always. And transaction history comes back in an envelope,
`{ items, page, pageSize, total, totalPages }`, not a bare array.

The full contract is in [`../APIDocs.txt`](../APIDocs.txt).
