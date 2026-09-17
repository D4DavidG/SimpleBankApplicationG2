# Frontend build plan

The brief's six screens, plus what auth adds. The scaffolding is done; this is
the plan for filling it in and who does what.

**The constraint that shapes everything below:** brevity. We are graded partly on
whether we can explain what we built. Every page here should be one file, under
about 120 lines, that one person can walk a room through. If a page is growing
past that, it is doing too much.

---

## 1. Where we are

Working: home, the account list, login, register, admin sign-in, admin
registration, and the profile page. Routing, the auth context, the route guard
and the API layer are done and tested against the live backend.

Stubbed: seven pages, one file each in `src/pages/`, each carrying a `TODO`
comment that names the API call it needs and the rules that apply.

## 2. The pages

| # | Route | File | Brief | Owner | Done |
| --- | --- | --- | --- | --- | --- |
| 1 | `/` | `Home.jsx` | 7.1 | David | ✅ public landing + dashboard |
| 2 | `/accounts` | `Accounts.jsx` | 7.1 | David | ✅ |
| 3 | `/login` | `Login.jsx` | bonus | David | ✅ |
| 4 | `/register` | `Register.jsx` | 7.2 | David | ✅ |
| 5 | `/profile` | `Profile.jsx` | — | David | ✅ |
| 6 | `/accounts/new` | `OpenAccount.jsx` | 7.2 | | |
| 7 | `/accounts/:id` | `AccountDetails.jsx` | 7.3 | | |
| 8 | `/accounts/:id/deposit` | `Deposit.jsx` | 7.4 | | ⚠️ see below |
| 9 | `/accounts/:id/withdraw` | `Withdraw.jsx` | 7.5 | | ⚠️ see below |
| 10 | `/accounts/:id/transactions` | `Transactions.jsx` | 7.6 | | |
| 11 | `/transfer` | `Transfer.jsx` | bonus | | ⚠️ see below |
| 12 | `/admin` | `Admin.jsx` | — | | |
| — | *(temporary)* `/transactions` | `TransactionMenu.jsx` | 7.4/7.5 + bonus | | ✅ built |

Put your name in the Owner column and in the `owner` prop on the page's `<Stub>`.

**⚠️ `TransactionMenu.jsx` already does deposit, withdraw and transfer** — one
component, one form, switched by a `kind` dropdown. So stubs 8, 9 and 11 are
probably not three pages any more. Somebody needs to decide which, and it is not
a decision to make silently:

- **Keep one screen.** Drop the three stubs and their routes; put the menu on the
  account detail page. Fewest lines, and the brief's 7.4 and 7.5 are then two
  states of one screen rather than two pages.
- **Keep three routes.** Each renders `TransactionMenu` with the kind preset.
  Matches the brief's wording literally, costs three thin files.

Either is defensible. Pick one before anyone starts building 8, 9 or 11,
because both of those people would otherwise be rewriting work that exists.

`TransactionMenu` takes its account as a **prop** and never fetches it, so
whoever wires it in owns fetching the account and calling `refreshAccounts()`
afterwards — see §3. It is currently reachable at `/transactions` on a temporary
public route with a hard-coded account, marked for deletion in `App.jsx`.

Note it is **not** `Transactions.jsx` (10), which is the history table.

**Styling is David's, and it comes last.** The shared tokens in `src/index.css`
are already set; leave the visual pass on your page until it works, then say so
and it gets picked up. Use the existing classes (`card`, `form`, `error`,
`hint`, `balance`, `badge`) rather than inventing new ones, and the pass will be
mostly free.

**Suggested split for what is genuinely still open:** 7 (account detail, which
is where the transaction menu probably lands), 10 (history table, the one page
with pagination), 12 (admin), and 6 (open account) wherever it fits.

## 3. Build order

0. **Settle the TransactionMenu question above first.** Everything else in this
   list assumes an answer to it.
1. **Account detail (7).** Mostly display, and it is the natural home for the
   transaction menu, so wiring the two together finishes three of the brief's
   five core capabilities at once.
2. **Transactions (10).** The history table, and the only page with pagination.
3. **Open account (6).** A two-field form.
4. **Admin (12).** Bonus surface.

Adding a page means a file in `src/pages/` and a line in `src/App.jsx`. Nothing
else.

**If your page moves money, call `refreshAccounts()` after it succeeds.** The
account list lives in the auth context because the nav bar and the home page
both read it; without the refresh, both keep showing the old balance.

```js
const { refreshAccounts } = useAuth()
// ... after a successful deposit/withdraw/transfer:
await refreshAccounts()
```

## 4. The rules that apply to every page

These are in `AGENTS.md` too, and they are the ones that actually cost us marks
if we get them wrong:

- **Cents in state, dollars only on screen.** `parseDollars` in, `formatCents`
  out. The API refuses `25.00` and `"2500"` rather than guessing.
- **Render the balance the server returned.** Never add the amount to the number
  you were holding.
- **One `crypto.randomUUID()` per submission** as `clientTxnId`, so a
  double-click cannot deposit twice.
- **Read `availableForWithdrawal`**, not `balance`, when offering an amount to
  withdraw.
- **Disable the submit button while the call is in flight** and show what is
  happening. `Login.jsx` has the pattern; copy it.

## 5. One deviation from the brief, on purpose

The brief's 7.4 and 7.5 are a single amount input and a submit button. We add a
review-and-confirm step: enter the amount, see a summary stating the action, the
amount and the account, then confirm.

WCAG 3.3.4 asks that a transaction involving money be reversible, checked, or
confirmed. Ours is not reversible, so it gets confirmed. It is two states in one
component, not a second page, and it prevents the likeliest user error in the
app. Worth the twenty lines.

## 5b. The home page

`/` is the only public route, and it is two pages in one `if`: a landing page
with the sign-in form for a visitor, the account summary once you are signed in.
Everything else still sits behind `RequireAuth`.

Signing in, registering and logging out all land here.

Pieces worth knowing about, because they are shared:

- `components/LoginForm.jsx` — the sign-in form. Used by the landing page *and*
  `/login`; two copies would drift apart.
- `components/AboutUs.jsx` — the team panel. Opening it animates because a grid
  row goes `0fr` → `1fr`, which is the one way to transition to a height nobody
  has measured; `height: auto` does not animate.
- `.lift` — the hover used by every pickable card and button: 5% bigger and a
  deeper shadow. One class, so the effect stays the same everywhere, and it
  drops the scaling under `prefers-reduced-motion`.
- **"Remember me" really does something.** Ticked, the token goes in
  `localStorage` and survives closing the browser; unticked, `sessionStorage`
  and it does not. The token still expires after an hour either way.

## 6. Theme

Citi's palette: deep navy `#003b70`, a brighter blue `#056dae` for links, and the
red from the arc over the "t" for errors and debits. All tokens are in
`src/index.css` with their contrast ratios recorded in comments beside them.

**The nav bar turns red in admin context** — when an admin is signed in, or the
route is under `/admin`. It works by putting `.theme-admin` on the `<header>`,
which redefines `--navy`, `--blue`, `--field-border` and `--bg` for everything
inside it. Custom properties inherit, so that one class recolours the whole
subtree and no component knows it happened — there is no second stylesheet. The
point is not decoration: you should be able to tell at a glance which context you
are in, because an admin can freeze accounts and adjust balances.

We use the colours and not the marks — no Citi logo, wordmark or name anywhere.
A practice page borrowing a palette is fine; one carrying a real bank's branding
is a different thing, and it is the kind of detail a reviewer notices.

Three rules carried into the CSS already:

- **Field borders clear 3:1** (`--field-border`, 3.66:1). WCAG 1.4.11, and this
  app is almost entirely form fields, so it is the one that matters most here.
- **Credits and debits carry a sign or a word, never colour alone.** Red/green
  is the most common colour-vision axis.
- **Focus outlines are never suppressed.** A keyboard-only user has to be able to
  complete a deposit.

Also: `tabular-nums` on every currency figure so a column of balances lines up,
and no animated balance counters — a number ticking up reads as alarming in a
bank.

## 7. The AI assistant

Worth building, and worth scoping tightly so it cannot hurt anything. Last, and
behind a flag, so an unfinished one is switched off and the demo is unaffected.

**What it is:** a panel that answers questions about *your own* accounts and
transactions. "What did I spend last week?" "Why was that withdrawal refused?"

**Read-only, with no exceptions.** It does not move money — not with a
confirmation, not at all. A natural-language interpreter in front of an
irreversible operation is the wrong shape. If we want it to help with a transfer,
it navigates the user to the pre-filled form and they complete it normally.

**It runs with the user's permissions, not the database's.** Three tools, each
filtered by the session user on the server, reusing the same ownership check the
REST routes already go through:

```
get_my_accounts()
get_my_transactions(accountId, from, to)
get_balance(accountId)
```

No free-form query tool, and specifically nothing that takes SQL. The model never
receives an account id it can vary freely — which means even a successful prompt
injection cannot reach another user's data.

**It cites the transaction ids it used, and it refuses when the data does not
support an answer.** A bank assistant that invents a balance is worse than one
that says it does not know. When we test it, a correct refusal counts as a pass.

**What it costs us:** one backend route, one tool-dispatch function, one panel
component. If it starts growing past that, it gets cut — see the constraint at
the top.

## 8. Before the demo

- [ ] Screenshots of every page, error and empty states included
- [ ] Keyboard-only walkthrough: log in, deposit, withdraw, log out
- [ ] Check the money column lines up with a five-digit balance beside a one-cent
      one — seed accounts 9 and 18 exist for exactly this
- [ ] `GET /api/admin/reconciliation` open in a tab, reading `balanced: true`
