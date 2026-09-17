# Frontend build plan

The brief's six screens, plus what auth adds. The scaffolding is done; this is
the plan for filling it in and who does what.

**The constraint that shapes everything below:** brevity. We are graded partly on
whether we can explain what we built. Every page here should be one file, under
about 120 lines, that one person can walk a room through. If a page is growing
past that, it is doing too much.

---

## 1. Where we are

Working: `/login`, `/register`, `/` (account list). Routing, the auth context,
the route guard and the API layer are done and tested against the live backend.

Stubbed: seven pages, one file each in `src/pages/`, each carrying a `TODO`
comment that names the API call it needs and the rules that apply.

## 2. The pages

| # | Route | File | Brief | Owner | Done |
| --- | --- | --- | --- | --- | --- |
| 1 | `/` | `Home.jsx` | 7.1 | — | ✅ |
| 2 | `/register` | `Register.jsx` | 7.2 | — | ✅ |
| 3 | `/login` | `Login.jsx` | bonus | — | ✅ |
| 4 | `/accounts/new` | `OpenAccount.jsx` | 7.2 | | |
| 5 | `/accounts/:id` | `AccountDetails.jsx` | 7.3 | | |
| 6 | `/accounts/:id/deposit` | `Deposit.jsx` | 7.4 | | |
| 7 | `/accounts/:id/withdraw` | `Withdraw.jsx` | 7.5 | | |
| 8 | `/accounts/:id/transactions` | `Transactions.jsx` | 7.6 | | |
| 9 | `/transfer` | `Transfer.jsx` | bonus | | |
| 10 | `/admin` | `Admin.jsx` | — | | |

Put your name in the Owner column and in the `owner` prop on the page's `<Stub>`.

**Suggested split for a team of four:** one person takes 4 + 5 (the account
pair), one takes 6 + 7 (they are near-identical, so build them together), one
takes 8 + 9, one takes 10. Whoever finishes first takes the confirm step in §5.

## 3. Build order

1. **6 and 7 first — deposit and withdraw.** They are the smallest complete
   loop: input, validate, call, render the returned balance. Getting them right
   settles the money handling, the error display and the pending state for
   everyone else, and they are two of the brief's five core capabilities.
2. **5, then 8.** Account details is mostly display. Transactions is the first
   page with pagination.
3. **4.** Opening an account is a two-field form.
4. **9 and 10.** Transfer and admin are bonus surface.

Adding a page means a file in `src/pages/` and a line in `src/App.jsx`. Nothing
else.

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

## 6. Theme

Citi's palette: deep navy `#003b70`, a brighter blue `#056dae` for links, and the
red from the arc over the "t" for errors and debits. All tokens are in
`src/index.css` with their contrast ratios recorded in comments beside them.

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
