# Thursday updates — 2026-09-17

Branch: `thursday`. Everything below is on it.

---

## 1. The frontend now exists

`frontend/` is a React + Vite app. Plain JavaScript, plain CSS, no UI library.
It is scaffolding, not a finished UI — the point was to get the plumbing working
so the team can divide up pages without four people each inventing their own way
to call the API.

Run it:

```bash
python server.py            # terminal 1
cd frontend && npm install  # once
npm run dev                 # terminal 2 -> http://localhost:5173
```

Log in as `aaron.forrester@example.com` / `BankDemo123!`.

### What works

| File | What it does |
| --- | --- |
| `src/lib/api.js` | One function per endpoint, all 17 routes. Handles the `Authorization` header, JSON encoding and the `{ error }` failure shape in one place. Nothing else should call `fetch`. |
| `src/lib/money.js` | `formatCents`, `parseDollars`, `formatDate`. |
| `src/context/AuthContext.jsx` | Login, register, logout, token in `localStorage`, re-checked against `/api/auth/me` on page load. |
| `src/components/RequireAuth.jsx` | Route guard, with an `admin` variant. |
| `src/App.jsx` | Every route in one table, mirroring the route table in `bank/api.py`. |
| `src/pages/Login.jsx`, `Register.jsx`, `Home.jsx` | Real pages, plain styling. |

Vite proxies `/api` to `127.0.0.1:8000`, so the browser sees one origin and there
is no CORS or base-URL configuration to do. Change the target in
`vite.config.js` if you run the backend on another port.

**Verified, not assumed:** `npm run build` and `npm run lint` are both clean;
login, `/api/auth/me` and `/api/accounts` all return correctly through the proxy;
deep links like `/accounts/1/deposit` fall through to `index.html`, so a refresh
does not 404.

### What is stubbed

Seven pages, one file each in `src/pages/`, each carrying a `TODO` naming the API
call it needs and the rules that apply. Claim one by putting your name in the
`owner` prop and in the table in `frontend/PLAN.md`.

`OpenAccount`, `AccountDetails`, `Deposit`, `Withdraw`, `Transactions`,
`Transfer`, `Admin`.

---

## 2. Theme: Citi colours

Deep navy `#003b70`, brighter blue `#056dae` for links, and the red from the arc
over the "t" for errors and debits. Tokens are in `frontend/src/index.css` with
their contrast ratios recorded in comments beside each one.

Ratios were computed rather than eyeballed. Everything passes AA except the
original card border, which came in at 1.42:1 — fine for a decorative divider,
not fine for a field you can type in. So there are two border tokens now:
`--border` for dividers and `--field-border` at 3.66:1 for anything interactive.
That is WCAG 1.4.11, and it is the criterion this app is most exposed to, since
it is almost entirely forms.

We use the palette and not the marks — no Citi logo, wordmark or name. Borrowing
a colour scheme for a practice project is ordinary; shipping a page that carries
a real bank's branding is a different thing and a reviewer would notice.

---

## 3. Code removed

Roughly 1,630 lines and two binaries, none of it reachable from the app or the
tests. **All 109 tests still pass.**

| Removed | Lines | Why |
| --- | ---: | --- |
| `console.py` | 891 | Interactive demo. The biggest single thing to explain, and `demo.py` covers the same rules without anyone typing. |
| `simulate.py` | 377 | Atlas traffic generator. Good to watch, not graded. |
| `tools/make_script_pdf.py` | 318 | Generates `script.pdf` and needs `reportlab`, which is not installed and is not in `requirements.txt`. It could not run as it stood. |
| `demo_mongo.py` | 39 | A raw `pymongo` spike that bypassed the whole architecture. Only user of `python-dotenv` in the repo. |
| `script.pdf` | — | Committed binary nobody can diff. |
| `playground-1.mongodb.js` | — | Scratch file. Already gitignored, but it is the usual way a connection string ends up committed. Deleted from disk. |

`README.md` had two sections and two table rows describing the removed tools;
those are gone. While in there I fixed a stale test count (107 → 109) and put
back a sentence about `demo.py --mongo` that a merge had stranded at the end of
the `simulate.py` prose.

Kept: `demo.py` (scripted walkthrough), `tools/check_mongo.py` (what to run when
Atlas will not connect — it explains what actually failed, which Atlas does not).

---

## 4. New documents

| File | What it is |
| --- | --- |
| `AGENTS.md` | Shared context and the running TODO list. Read before starting work. |
| `frontend/PLAN.md` | The frontend build plan: pages, owners, build order, theme, the AI assistant. |
| `thursdayupdates.md` | This file. |

`AGENTS.md` was in `.gitignore` under "AI customization files". It is the team's
shared TODO now, so it has to be in the repo everyone clones — I un-ignored it.
`.github/` is still ignored.

The instructor's brief in `Simple_Bank_Application_Project.md` is untouched, so
it stays quotable as the original. The plan lives beside the code it describes.

---

## 5. What still has to happen

Full list in `AGENTS.md`. The four that are actually graded:

1. **The seven frontend pages.** Split and build order in `frontend/PLAN.md`.
   Deposit and withdraw first — they are the smallest complete loop and settle
   the money handling for everyone else.
2. **The SQL script.** It is a submission requirement and it is not in the repo.
   The schema and inserts are written and verified in `seed_data_bank_app.md`
   §3–4; they need extracting to `sql/`. Note that document's amounts are
   `DECIMAL` and ours are integer cents — decide which the script reflects.
3. **UI screenshots.** A submission requirement. Capture per feature as it lands,
   error and empty states included, rather than scrambling the night before.
4. **MySQL or MongoDB.** Still open, and it decides what item 2 actually is.
   This needs an instructor answer, not a guess.

---

## 6. The AI assistant

Worth building. Scoped in `frontend/PLAN.md` §7, and the scoping is the
important half:

- **Read-only.** It answers questions about your own accounts. It does not move
  money — not with a confirmation step, not at all.
- **Three tools**, each filtered by the session user on the server, reusing the
  ownership check the REST routes already go through. No free-form query tool.
  The model never sees an account id it can vary, so even a successful prompt
  injection cannot reach another user's data.
- **It cites the transaction ids it used and refuses when the data does not
  support an answer.** A correct refusal counts as a pass when we test it.

Cost: one backend route, one tool-dispatch function, one panel component. Built
last and behind a flag, so if it is not finished it is switched off and the demo
is unaffected.

---

## 7. Decisions I made that you may want to reverse

- Dropped `console.py` on the aggressive-prune option. It was commented
  throughout two commits ago, so if that work was for the demo rather than for
  tidiness, it is one `git revert` away.
- Put the frontend plan in `frontend/PLAN.md` rather than appending it to the
  brief, to keep the brief verbatim.
- The confirm step on deposit and withdraw (`PLAN.md` §5) is a deliberate
  deviation from brief 7.4 and 7.5. It is twenty lines and satisfies WCAG 3.3.4.
  Worth mentioning to the instructor rather than letting them find it.
