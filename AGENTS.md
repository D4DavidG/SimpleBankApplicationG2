# AGENTS.md

Shared context and the running TODO list. Read this before starting work, human
or AI. If something here is out of date, fix it in the same commit as the code
that made it out of date.

## The one rule that outranks the others

**Brevity.** This is a training project and it is graded partly on whether we can
explain it. A feature nobody on the team can walk a room through is worse than no
feature. Before adding anything, ask whether it earns the lines it costs.

---

## Where we are

| Layer | State |
| --- | --- |
| Domain, services, repository | Done. 125 tests, 14 skip without a Mongo cluster. |
| REST API | Done. 18 routes, `bank/api.py`. Contract in `APIDocs.txt`. |
| Auth | Done. Register, login, `/api/auth/me`, signed tokens, ADMIN role. |
| Database | Done for MongoDB Atlas. In-memory fallback. **MySQL not started.** |
| Frontend | Routing, auth, API layer, and 7 real pages (home, accounts, login, register, profile, admin sign-in, admin register). 7 stubs left. |

Run it: `python server.py` in one terminal, `cd frontend && npm run dev` in
another. Seed login `aaron.forrester@example.com`, password `BankDemo123!`.

---

## TODO

### Must ship — these are graded

- [ ] **Frontend pages.** Seven stubs in `frontend/src/pages/`, one file each.
      Plan and owner table: [frontend/PLAN.md](frontend/PLAN.md).
- [ ] **SQL script.** A submission requirement and it does not exist in the repo.
      The schema and inserts are written and verified in the team's
      `seed_data_bank_app.md` planning doc, §3–4. Extract to `sql/schema.sql`
      and `sql/seed.sql`. Its amounts are `DECIMAL`; ours are integer cents, so
      decide which the script reflects and say so in a comment.
- [ ] **UI screenshots.** A submission requirement. Capture per feature as it
      lands, including error and empty states, not just the happy path.
- [ ] **Decide MySQL or MongoDB.** Open since day one. It changes what the SQL
      script above actually is. Ask the instructor; do not guess.

### Should ship

- [ ] **Confirm step on deposit and withdraw.** WCAG 3.3.4 asks that a money
      transaction be reversible, checked, or confirmed. A review-then-confirm
      step is the cheap way to satisfy it and prevents the app's most likely
      user error. Two states in one component, not a second page.
- [ ] **Validation messages on the UI.** On the brief's bonus list. Errors tied
      to their field with `aria-describedby`, never signalled by border colour
      alone.
- [ ] **Empty and loading states** on every page that fetches.

### Stretch — only after the above are demoable

- [ ] **AI assistant.** Scoped in [frontend/PLAN.md](frontend/PLAN.md). Read-only,
      three tools, session-scoped. Behind a flag so an unfinished one is switched
      off and the demo is unaffected.
- [ ] **Deployment**, if the program expects it. Unconfirmed.

### Deliberately not doing

Refresh tokens, httpOnly cookie sessions, rate limiting on login, and a second
account-type minimum balance. All are the right end state and none is graded.
They are listed in README §13 with the reasoning.

---

## Conventions that will bite you

**Money is an integer number of cents.** `123456` is `1,234.56`. The API refuses
`25.00` and `"2500"` with a 400 rather than guessing, because guessing wrong is a
hundredfold error. In the frontend: `parseDollars` on the way in, `formatCents`
on the way out, cents in state, no arithmetic on dollars.

**Never compute a balance in the browser.** Every write endpoint returns the new
authoritative account beside the transaction. Render that.

**Ownership is checked server-side on every account-scoped route**, and an
account belonging to someone else reads as 404, not 403. Do not add a route that
takes an account id without going through `service.get_account_for`.

**The ledger is append-only.** A correction is a new entry in the opposite
direction. If you ever write an update to a transaction, the design has gone
wrong. `GET /api/admin/reconciliation` is the running proof and should always
come back `balanced: true`.

**Send a `clientTxnId`** on deposit, withdraw and transfer — one
`crypto.randomUUID()` per submission attempt, so a double-click cannot move the
money twice.

**Call `refreshAccounts()` after moving money.** The account list lives in the
auth context because the nav bar and the home page both read it. A deposit,
withdrawal or transfer that does not refresh it leaves both showing the old
balance. `const { refreshAccounts } = useAuth()`.

**Admin role comes from `BANK_ADMIN_CODE`, checked server-side.** Registering
with a matching `adminCode` creates an ADMIN. Never check that code in the
browser — anything in the bundle is readable with Ctrl+U. See `api._role_for`.

**All backend code is standard library only.** `requirements.txt` exists for
pymongo and nothing else. Keep it that way.

---

## Where things are

| Path | What |
| --- | --- |
| `bank/` | The backend. `api.py` has the route table; `services.py` has the rules. |
| `APIDocs.txt` | The API contract. The frontend's source of truth. |
| `frontend/` | React + Vite. See its README and PLAN. |
| `test_*.py` | 125 tests. `python -m unittest -q`. |
| `tools/check_mongo.py` | Run when Atlas will not connect. It explains what failed. |
