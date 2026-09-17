# Simple Bank Application: frontend

React + Vite. Plain JavaScript, plain CSS, no UI library. This is the scaffolding
only: routing, authentication and the API layer work, and the pages themselves
are stubs waiting to be claimed.

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
| `src/lib/api.js` | One function per endpoint. Handles the `Authorization` header, JSON encoding and the `{ error }` failure shape. **Do not call `fetch` from a page.** |
| `src/lib/money.js` | `formatCents`, `parseDollars`, `formatDate`. |
| `src/context/AuthContext.jsx` | Login, register, logout, the stored token, the profile edit, and the account list. |
| `src/context/auth-context.js` | The `useAuth()` hook. |
| `src/components/RequireAuth.jsx` | Route guard: redirects to `/login`, or away from `/admin` for a non-admin. |
| `src/components/Layout.jsx` | Nav bar and page frame. |
| `src/App.jsx` | Every route, in one table. |
| `src/index.css` | Placeholder styles. Nobody is attached to these. |

Working already: `/` (home), `/accounts`, `/login`, `/register`, `/profile`,
`/admin/login` and `/admin/register`. They are plain but real, so the pages you
build have live data and real account ids to work against.

### Staff accounts

The two pages at `/admin/login` and `/admin/register` are reached from the small
link in the bottom-left corner of the customer login and register pages, and they
are red rather than navy so the context is obvious.

Registering there asks for a team code. The code is **not** checked in the
browser — it is sent to the server as `adminCode` and compared against
`BANK_ADMIN_CODE` from `.env`. A check written in JavaScript would ship inside
the bundle where anyone can read it, and would stop nobody. If `BANK_ADMIN_CODE`
is not set, admin registration is closed and any code is refused.

## What is waiting to be claimed

Pages, owners and build order: **[PLAN.md](PLAN.md)**.

One page per file in `src/pages/`. Each stub carries a `TODO` comment naming the
API call it needs and the rules that apply to it. Put your name in the `owner`
prop on the `<Stub>` when you take one, and delete the whole stub when you build
the real thing.

| Route | File | Brief |
| --- | --- | --- |
| `/accounts/new` | `OpenAccount.jsx` | 7.2 |
| `/accounts/:accountId` | `AccountDetails.jsx` | 7.3 |
| `/accounts/:accountId/deposit` | `Deposit.jsx` | 7.4 |
| `/accounts/:accountId/withdraw` | `Withdraw.jsx` | 7.5 |
| `/accounts/:accountId/transactions` | `Transactions.jsx` | 7.6 |
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
