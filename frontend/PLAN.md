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

Every screen in brief §7 now exists.

| Route | File | Brief | Done |
| --- | --- | --- | --- |
| `/` | `Home.jsx` | 7.1 | ✅ landing + dashboard |
| `/accounts` | `Accounts.jsx` | 7.1 | ✅ |
| `/accounts/new` | `OpenAccount.jsx` | 7.2 | ✅ |
| `/register` | `Register.jsx` | 7.2 | ✅ |
| `/login` | `Login.jsx` | bonus | ✅ |
| `/profile` | `Profile.jsx` | — | ✅ |
| `/accounts/:id` | `AccountDetails.jsx` | 7.3 | ✅ |
| `/deposit`, `/accounts/:id/deposit` | `Deposit.jsx` | 7.4 | ✅ |
| `/withdraw`, `/accounts/:id/withdraw` | `Withdraw.jsx` | 7.5 | ✅ |
| `/history`, `/accounts/:id/transactions` | `History.jsx`, `Transactions.jsx` | 7.6 | ✅ |
| `/transfer` | `Transfer.jsx` | bonus | ✅ |
| `/admin` | `Admin.jsx` | — | ✅ |

`TransactionMenu.jsx` is the shared money form. Deposit and Withdraw render it
with `fixedKind`, which is why the amount parsing, the `clientTxnId` and the
"render the balance the server returned" rule exist once rather than three times.

**Naming and colour live in `src/lib/accounts.js`.** `accountLabel` gives
`Checking...23`; `accountTone` gives the colour class. Both are imported rather
than re-derived, because an account that is teal in one list and violet in
another is worse than one with no colour at all.

**Credit accounts** are always blue with yellow type and a yellow glow, outside
the six-colour rotation, because they are a different product rather than
another account of the same kind. Note the backend limit: `CreditAccount` cannot
go negative, so today it behaves exactly like a checking account. Making it a
real credit line means a credit limit and a negative `minimum_balance`, and its
docstring says where to start.

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
  and it does not. The token still expires after a week either way.

## 5c. Where to change the spacing

All of it is in `:root` at the top of `src/index.css`. Five steps, each about
1.5x the last, and every gap and pad on the site uses one of them:

| Token | What it spaces |
| --- | --- |
| `--s1` | inside a control, icon to text |
| `--s2` | between fields in a form |
| `--s3` | card padding, and the gap between cards |
| `--s4` | one section of a page to the next |
| `--s5` | around something standing alone, like About us |
| `--page-w` | how wide the content runs before it stops — the nav uses it too, so the brand lines up with the page |

Change one of those and the whole site moves together. Adding a sixth value
because something "needs a bit more" is how a page ends up with 13px next to
14px next to 16px, so reach for the next step up instead.

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

**The account bars are six fixed colours** (`.bar-0` … `.bar-5` in
`index.css`), picked by `accountId % 6` so an account keeps its colour between
visits. Each one is a gradient, and white text clears 4.5:1 at the *lightest*
end of every one of them — the ratio is written beside each rule. If you add a
seventh colour, compute it before you commit it; a pastel cannot carry white
text, which is why these are saturated rather than pale.

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
