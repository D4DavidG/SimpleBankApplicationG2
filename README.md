# Simple Bank Application: Backend

A banking backend with a REST API, authentication, an immutable ledger, and an
admin surface. Pure Python, standard library only. **Nothing to `pip install`.**

```bash
python demo.py                     # walkthrough of every rule, no server needed
python demo.py --step              # the same, paused between sections, for presenting
python demo.py --step --mongo      # ... against Atlas, ending in a persistence proof
python -m unittest -q              # 144 tests (16 Mongo ones skip without a cluster)
python server.py                   # REST API on http://127.0.0.1:8000
cd frontend && npm run dev         # React UI on http://localhost:5173 (needs the API up)
python tools/export_postman.py     # regenerate postman_collection.json
```

Requires Python 3.10 or newer (the code uses `str | None` type syntax).

Starting work? Read **[AGENTS.md](AGENTS.md)** first: current state, the TODO
list, and the conventions that will bite you. Frontend plan:
**[frontend/PLAN.md](frontend/PLAN.md)**.

---

## Table of contents

1. [What this is and what it is not](#1-what-this-is-and-what-it-is-not)
2. [Quick start](#2-quick-start)
3. [Architecture: the layers and why they are separate](#3-architecture-the-layers-and-why-they-are-separate)
4. [Every file, and what it does](#4-every-file-and-what-it-does)
5. [The API](#5-the-api)
6. [Authentication and authorization](#6-authentication-and-authorization)
7. [Money: the rules that make this a bank and not a CRUD app](#7-money-the-rules-that-make-this-a-bank-and-not-a-crud-app)
8. [Business rules enforced](#8-business-rules-enforced)
9. [Error handling: one table, one place](#9-error-handling-one-table-one-place)
10. [Seed data](#10-seed-data)
11. [Testing](#11-testing)
12. [Design decisions worth defending in review](#12-design-decisions-worth-defending-in-review)
13. [What is deliberately not done yet](#13-what-is-deliberately-not-done-yet)
14. [Open questions for the instructor](#14-open-questions-for-the-instructor)
15. [Submission checklist](#15-submission-checklist)

---

## 1. What this is and what it is not

| | |
| --- | --- |
| **Is here** | Domain model, business rules, in-memory repository, password hashing, signed JWT sessions, a REST API with 18 routes, role-based authorization, a persisted audit log, seed data, 144 tests, a MongoDB Atlas repository, a scripted demo, a generated Postman collection |
| **Not here** | A database, a finished frontend, any third-party package on the Python side |

The backend still imports nothing but the standard library, and
`python server.py` still runs on a clean machine with nothing installed.
`requirements.txt` exists for the database phase only: the MongoDB store imports
pymongo, and it is imported only when `.env` asks for it. See [mongo.md](mongo.md).

The brief's architecture diagram is:

```
Frontend (UI) -> REST API (Controller) -> Service Layer -> Repository -> Database
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                 this repository, with the Database part held in memory
```

The layers are separate in a way that can be checked rather than asserted:
`test_bank.py` exercises every business rule in the system without importing
`api.py` at all. If a rule ever moves into a request handler, that test file can
no longer reach it.

---

## 2. Quick start

### Run the demo (no server, no setup)

```bash
python demo.py
```

Eleven sections. Sections 1 to 10 call service methods and print what each rule
did; section 11 reaches the same rules through the HTTP layer so the rules and
their status codes appear side by side. Nothing to type, nothing to clean up.

**Presenting it to a room:**

```bash
python demo.py --step              # stops before each section, waits for Enter
python demo.py --step --mongo      # ... and stores it all in MongoDB Atlas
```

`--step` exists so the narration happens between sections instead of racing a
wall of scrolling output.

`--mongo` adds a twelfth section that opens a **second,
independent connection** and reads the balances and the audit log back out of
Atlas — the one claim the in-memory version cannot make. It uses its own
`simple_bank_demo` database and wipes it on the way in, so it never touches the
shared data and can be run twice.

### Run the API

```bash
python server.py
```

```
  seeded 14 users, 20 accounts, 73 transactions
  all accounts reconcile: balance == sum(ledger)

  every seeded user's password is: BankDemo123!
  customer login: aaron.forrester@example.com
  admin logins:   bianca.alvarado@example.com, david.gusmao@example.com

  Simple Bank API listening on http://127.0.0.1:8000
```

Then:

```bash
# log in and keep the token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"aaron.forrester@example.com","password":"BankDemo123!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s http://127.0.0.1:8000/api/accounts -H "Authorization: Bearer $TOKEN"
```

Flags: `--port 9000`, `--host 0.0.0.0`, `--empty` (start with no seed data).

### Run it from Postman

Import `postman_collection.json`, run **Auth > Login (customer)**, then anything
else — the login request's test script stores the token in a collection variable
that every other request sends automatically.

---

## 3. Architecture: the layers and why they are separate

Each layer depends only on the one below it. Nothing points back up.

```
  api.py            Controller.  HTTP in, JSON out.  NO business rules.
       |
  serializers.py    Domain objects -> JSON dicts.  Money leaves as int cents.
       |
  services.py       Every business rule.  NO HTTP, NO SQL, NO framework.
       |
  models.py         User, Account, Transaction.  Plain Python classes.
       |
  store.py          Repository.  In-memory today, a database later.
```

Supporting modules sit to the side, used by several layers:
`money.py` (cents as ints), `security.py` (hashing and tokens),
`errors.py` (domain exceptions), `seed.py` (demo data).

**Why this matters for grading.** "Clean MVC separation" is one of the four
evaluation criteria, and it is rarely lost to a grand architectural mistake. It is
lost one `if` at a time, each of which looked easier to put in the handler than to
thread through the service. Three concrete rules this repo follows:

- A controller does exactly four things: identify the caller, read the request,
  call **one** service method, turn the result or exception into a status code.
- A service raises `InsufficientFunds`, never a `409`. It does not know HTTP
  exists.
- A model enforces its own invariants. `Account.balance` has no setter.

**What changes when the database arrives:** `store.py`, and nothing else. The
method names stay, the bodies become SQL. That is the whole reason it is a class
with methods instead of the services using dictionaries directly.

---

## 4. Every file, and what it does

Every module has a docstring explaining its job and the decisions inside it; this
table is the index.

### The package

| File | What it does |
| --- | --- |
| [bank/money.py](bank/money.py) | **Read this first.** Money is an `int` number of cents, never a `float` and never a `Decimal`. `to_cents()` refuses anything that is not an int; `parse_amount()` validates anything that came from outside the program; `format_money()` is display only. |
| [bank/errors.py](bank/errors.py) | The domain exceptions. Business concepts, not HTTP codes. Every class is empty on purpose — the type *is* the information. |
| [bank/models.py](bank/models.py) | `User`, `Account`, `Transaction`. `Account.balance` is a read-only property; `SavingsAccount` overrides `minimum_balance` so the withdrawal rule is polymorphic rather than an `if`. |
| [bank/store.py](bank/store.py) | The repository. Dictionaries and lists behind method names a database will later implement. Owns the id sequences (`AUTO_INCREMENT`), the email uniqueness index, and the `client_txn_id` set. |
| [bank/security.py](bank/security.py) | Password hashing (PBKDF2-HMAC-SHA256, salted, 600,000 rounds) and JSON Web Tokens (HS256 over base64url JSON, signature verified before the payload is parsed, algorithm pinned). |
| [bank/services.py](bank/services.py) | **Every business rule.** Register, authenticate, open account, deposit, withdraw, transfer, history, freeze, adjust, reconcile. Takes a lock around anything that moves money. |
| [bank/serializers.py](bank/serializers.py) | Domain objects to JSON dicts. Money goes out as **integer cents**. `password_hash` goes out never. |
| [bank/api.py](bank/api.py) | The controller: the route table, the token check, the role check, the error-to-status map, and the `http.server` plumbing at the bottom. |
| [bank/seed.py](bank/seed.py) | The cohort roster as demo data — 14 users, 20 accounts, 73 transactions — replayed through the real service methods and verified against independently computed balances. |
| [bank/\_\_init\_\_.py](bank/__init__.py) | The package's public surface. |

### Around it

| File | What it does |
| --- | --- |
| [server.py](server.py) | Entry point. Composes store → service → API, seeds, and serves. |
| [demo.py](demo.py) | Console walkthrough of every rule, then the same rules over HTTP. `--step` pauses between sections for presenting; `--mongo` runs it against Atlas and ends by reading everything back through a second connection. |
| [test_bank.py](test_bank.py) | 34 tests of the business rules. Imports no HTTP anything. |
| [test_api.py](test_api.py) | 59 tests of the controller: routing, auth, error mapping, serialization, the seed, and one end-to-end pass over a real socket. |
| [tools/export_postman.py](tools/export_postman.py) | Generates `postman_collection.json` **from the live route table**, so it cannot drift from the code. |
| [bank/config.py](bank/config.py) | Reads `.env` into the environment. Thirty lines of standard library; a real environment variable always wins over the file. |
| [bank/mongo_store.py](bank/mongo_store.py) | **The MongoDB repository.** Same methods as `store.py`, backed by Atlas. Ids from a `counters` collection, email uniqueness and idempotency from unique indexes, every change inside `atomic()` — a real multi-document transaction. Driver errors are translated to domain errors, so `api.py` answers 503 and 409 without importing pymongo. Imported only when `MONGODB_URI` is set, so pymongo stays optional. |
| [test_mongo.py](test_mongo.py) | 12 tests against a live cluster, opt-in with `MONGO_TESTS=1`. Always uses `simple_bank_test`, whatever `MONGODB_DB` says. Re-reads every balance from the database rather than trusting the returned object, and runs eight withdrawals across two connections to prove an account cannot be overdrawn. |
| [tools/check_mongo.py](tools/check_mongo.py) | Seven checks that this machine can use the Atlas cluster, ending with a real multi-document transaction. Run it after following `mongo.md`. |
| [postman_collection.json](postman_collection.json) | 28 requests in 6 folders, including a "Failure cases" folder. Generated — edit the tool, not this. |
| [mongo.md](mongo.md) | **MongoDB Atlas setup.** What each of us does to get a working connection, the decisions already made, and the reasoning. Start here for the database phase. |
| [requirements.txt](requirements.txt) | Empty of anything the *backend* needs. Exists for the database phase: `pymongo` is the first third-party package this project has required. |
| [.env.example](.env.example) | Committed. `.env` is not. Nothing is required to run. |

---

## 5. The API

18 routes. The five the brief specifies are marked ★.

### Auth

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | — | Create a user, return a token. An `adminCode` matching `BANK_ADMIN_CODE` makes them an ADMIN |
| `POST` | `/api/auth/login` | — | Exchange email + password for a token |
| `GET` | `/api/auth/me` | token | Who the current token belongs to |
| `POST` | `/api/auth/me` | token | Edit your own name or email |
| `GET` | `/api/health` | — | Liveness check |

### Accounts

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/accounts` | token | ★ Create an account |
| `GET` | `/api/accounts` | token | List the caller's accounts |
| `GET` | `/api/accounts/{id}` | token | ★ Account details |
| `POST` | `/api/accounts/{id}/deposit` | token | ★ Deposit |
| `POST` | `/api/accounts/{id}/withdraw` | token | ★ Withdraw |
| `GET` | `/api/accounts/{id}/transactions` | token | ★ History, paginated |
| `POST` | `/api/transfers` | token | Transfer between accounts |

### Admin (ADMIN role required — 403 otherwise)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/admin/users` | Every user |
| `GET` | `/api/admin/accounts` | Every account |
| `POST` | `/api/admin/accounts/{id}/freeze` | Freeze or unfreeze, with a written reason |
| `POST` | `/api/admin/accounts/{id}/adjust` | Post a correcting ledger entry |
| `GET` | `/api/admin/audit` | Who did what, to which account, and why |
| `GET` | `/api/admin/reconciliation` | Every account where balance ≠ sum(ledger) |

**There is no route that sets a balance, and there should never be one.** An
admin adjustment posts a normal transaction row tagged with the acting admin and
a reason, so `balance == sum(ledger)` still holds afterwards. A balance set
directly breaks that invariant permanently and leaves no way to tell which of the
two numbers was right. `test_api.py` has a test that fails if such a route
appears.

### Example: deposit

```http
POST /api/accounts/1/deposit
Authorization: Bearer <token>
Content-Type: application/json

{"amount": 10000, "clientTxnId": "a3f1-...-9c2e"}
```

```json
{
  "transaction": {
    "txnId": 74, "accountId": 1, "type": "DEPOSIT",
    "amount": 10000, "signedAmount": 10000, "direction": "CREDIT",
    "clientTxnId": "a3f1-...-9c2e", "createdAt": "2026-09-15T14:22:01+00:00"
  },
  "account": {
    "accountId": 1, "userId": 1, "userName": "Aaron Forrester",
    "accountType": "CHECKING", "status": "ACTIVE",
    "balance": 258000, "availableForWithdrawal": 258000,
    "minimumBalance": 0, "createdAt": "..."
  }
}
```

That deposit is 100.00 and the resulting balance is 2,580.00.

Three things in that response are deliberate:

- **Every money field is an integer number of cents.** See
  [section 7](#7-money-the-rules-that-make-this-a-bank-and-not-a-crud-app).
- **The whole account comes back,** not just the transaction. The client must
  never compute a new balance by adding the amount to the one it was holding —
  that is the frontend doing money arithmetic, and it is wrong the moment two
  tabs are open. One request, one authoritative balance.
- **`availableForWithdrawal` is sent alongside `balance`.** For a savings account
  they differ. Sending both keeps the minimum-balance rule in the `SavingsAccount`
  subclass instead of duplicated into the UI.

### Two deliberate deviations from the brief

**1. `POST /api/accounts` takes the owner from the token, not the body.**

The brief's sample body is `{"userId": 1, "accountType": "SAVINGS"}`. Taking the
owner from the body means any caller can open an account in somebody else's name
by changing that number. So the owner is the authenticated user, and `userId` is
honoured only when an admin is opening an account on a customer's behalf. The
brief's exact body still works; it just no longer works for a customer targeting a
stranger.

**2. Amounts are whole cents, and anything else is rejected with 400.**

The brief's sample is `{"amount": 500}`, meaning five hundred dollars. Here that
same body means five dollars, because the unit is cents throughout — five hundred
dollars is `{"amount": 50000}`.

Two forms are refused rather than interpreted:

- `{"amount": 500.00}` — a fractional JSON number parses to a Python float, which
  has already lost precision by the time the server sees it.
- `{"amount": "500.00"}` — a dollars-and-cents string, which is what an earlier
  version of this API accepted.

Both are ambiguous in an API that speaks cents, and guessing wrong is a
hundredfold error in one direction or the other. A 400 with a message saying so
is the only safe answer.

---

## 6. Authentication and authorization

The brief lists login under "Bonus Enhancements". The hiring manager asked for an
admin login and a normal user login, which moves it into core scope and adds an
authorization requirement to every endpoint that already existed.

### Passwords

PBKDF2-HMAC-SHA256, per-user random salt, 600,000 rounds. Stored as one
self-describing string:

```
pbkdf2_sha256$600000$<salt-b64>$<derived-key-b64>
```

The round count travels inside the hash, so it can be raised later without
invalidating existing users.

**Why not bcrypt?** It is the right answer and it is not in the standard library.
`hash_password` / `verify_password` is a two-function surface, so swapping in
bcrypt or argon2 means rewriting two bodies and nothing else. What is never
acceptable in any variant is a bare SHA-256: a plain hash is *fast*, which is
exactly the property an attacker wants.

### Sessions

A **JSON Web Token**, hand-rolled in [bank/security.py](bank/security.py) because
PyJWT is a third-party package and this submission installs nothing. Three
base64url parts:

```
header.payload.signature
```

| part | contents |
| --- | --- |
| header | `{"alg":"HS256","typ":"JWT"}` |
| payload | `{"sub":7,"username":"aaron@…","name":"Aaron Forrester","role":"CUSTOMER","iat":…,"exp":…}` |
| signature | `HMAC-SHA256(secret, "header.payload")` |

**Base64 is encoding, not encryption.** Anyone holding the token can decode the
payload and read every claim, with no key involved. A JWT keeps nothing secret,
so nothing sensitive goes in one. What it provides is *integrity*: the signature
is computed with a key only the server has, and HMAC is one-way, so **anybody can
read the claims and only the server can write them.** A customer who decodes
their token, edits `"role":"CUSTOMER"` to `"ADMIN"` and re-encodes it cannot
produce a matching signature, and `read_token` rejects it.

`read_token` does the two checks in the order that matters:

1. **Signature** — recompute the HMAC over the first two parts *as received* and
   compare with `hmac.compare_digest`. Constant-time, because a normal `==`
   returns as soon as two bytes differ and how long it takes leaks how much of a
   forgery was right.
2. **Expiration** — only now parse the payload and check `exp`.

Reversing that order means reading an `exp` the attacker chose.

It also **pins the algorithm** rather than believing the header. The classic JWT
break is `{"alg":"none"}` — a token declaring itself unsigned, which libraries
used to accept. There is a test for it.

### The one thing a JWT cannot do

**Be revoked.** The server signs a token and forgets it, so there is no record to
delete; it is valid until it expires, whatever happens to the user meanwhile.
That is the cost of being stateless, and it is why one rule is absolute here:

> **The `role` claim is never what authorizes.** `api._authenticate` re-reads the
> `User` from storage and checks the *stored* role. A user demoted an hour after
> logging in still carries a signed token saying ADMIN — and loses their powers
> on the very next request anyway.

The claim exists so a client can render the right menu without a round trip.
Nothing is decided by it.

**Tokens live for one week** (`TOKEN_TTL_SECONDS`, the one constant to edit). A
demo decision, not a security one: at an hour, a token saved in Postman or a tab
left open over a weekend came back 401 mid-demonstration. Be clear what it costs,
given the paragraph above — a leaked token is usable for a week and cannot be
cancelled short of changing `BANK_SECRET`, which logs out every user at once.
Acceptable for a graded project with a seeded roster; not for real money. §13 has
the end state.

### The signing key sets itself up

`python server.py` generates a key on first run and appends it to your `.env`,
which is gitignored. Tokens then survive a restart with no setup step, and the
startup banner says whether the key was found or just created.

**Each developer gets their own, and it is deliberately not shared.** A token is
only ever presented to the server that signed it, and everybody runs their own
backend on localhost, so a key that never leaves one machine works perfectly and
is one fewer secret in a group chat. A deployed server is the case that needs a
fixed key — it would set `BANK_SECRET` in its own environment, and
[`config.ensure_secret`](bank/config.py) finds it already set and leaves it alone.

Deleting the line issues a new key. That is also the only way to revoke a token
early, and it revokes every token at once, since they were all signed with the
old one.

### Ownership: the vulnerability in the brief as written

`GET /api/accounts/{id}` takes an account id and returns the account. Once there
are logins, a logged-in user can change the number in the URL and read somebody
else's balance. This has a name — insecure direct object reference — and this
project shape is where it usually appears.

The check lives in exactly one method, `BankService.get_account_for`, which every
read and write path already goes through. No route implements it, so no route can
forget it.

```python
account = self.store.get_account(account_id)
if account.user_id != actor.user_id and not actor.is_admin:
    raise AccountNotFound(f"no account with id {account_id}")
```

**It raises "not found", not "forbidden".** A distinct 403 confirms the account
exists, which is itself a leak. There is a test asserting the two error messages
are character-for-character identical after normalising the id.

---

## 7. Money: the rules that make this a bank and not a CRUD app

### Money is an integer number of cents, and never a float

```python
>>> 1000.10 + 234.20 + 0.30 - 0.04
1234.5599999999999
```

A float cannot represent 0.10 exactly, so sums drift, and the drift compounds
across a ledger. The same figures as cents — `100010 + 23420 + 30 - 4` — come to
`123456`, exactly, because integer arithmetic has no other option.

Four places this can go wrong, and what this codebase does at each:

| Where | Rule here |
| --- | --- |
| Storage | `BIGINT` cents when the database lands. Not `FLOAT`, not `DOUBLE`, not SQLite `NUMERIC`. |
| Application | `int` everywhere. `to_cents()` raises `TypeError` on a float rather than rounding it — by the time a float arrives it has already lost precision, so accepting it hides the bug. |
| JSON | **Serialized as an integer.** `"balance": 123456`, never `1234.56`. A fractional JSON number becomes an IEEE 754 double the instant `JSON.parse` runs; an integer is exact to 2^53, which is about ninety trillion dollars in cents. |
| Frontend | Divide by 100 to display, never to calculate. Render the balance the server sent; send amounts back as whole cents. |

The JSON row is the one most commonly missed, and getting it wrong discards the
precision every other layer was careful about.

**Why not `Decimal`?** It is the other correct answer, and it is what this
codebase used at first. `Decimal` is exact, but only if every value is quantized
to two places on the way in — miss one `.quantize()` and a third decimal place
survives to be rounded inconsistently later. An `int` cannot hold a third decimal
place at all, so the rule is enforced by the type rather than by remembering to
call something. `Decimal` also is not JSON-serializable, which is what forced the
earlier string-on-the-wire design; integers cross JSON intact.

### Every balance change writes exactly one ledger entry

`accounts.balance` is the stored source of truth, and `transactions` is the
append-only ledger behind it. The invariant is:

```
balance == sum(deposits) - sum(withdrawals)
```

`reconcile_all()` returns every account where that fails. It should always be
empty, and **every test in both suites asserts it in `tearDown`**, so a rule that
changes a balance without writing an entry fails the test that exercised it
rather than passing quietly. `GET /api/admin/reconciliation` exposes the same
check at runtime — that is the endpoint to open during the demo.

The ledger is append-only. `Transaction` rows are never updated and never
deleted; a correction is a new row of the opposite direction. If anyone ever
writes `UPDATE transactions`, something has gone wrong in the design.

### The double-clicked submit button

A slow response, an impatient user, and a second click is enough to deposit
twice. The client generates a UUID per submission attempt and sends it as
`clientTxnId`; the second one is refused with 409.

In memory that is a set lookup. In the database it becomes a `UNIQUE` index on
`transactions.client_txn_id`, which is the version that holds under concurrency.

### Concurrency

The API server is threaded, so two requests genuinely can run at once, and the
natural "read the balance, check it, write the new balance" sequence lets two
simultaneous withdrawals both pass the check and both write. `BankService` takes
an `RLock` around everything that moves money.

**This is the one rule that gets weaker when the database arrives**, because a
lock inside one process does not coordinate two processes. The fix is a single
conditional statement, which is both correct and easy to explain in a demo:

```sql
UPDATE accounts
   SET balance = balance - :amount
 WHERE account_id = :id
   AND status = 'ACTIVE'
   AND balance >= :amount;
-- affected rows = 0  ->  insufficient funds, or frozen. Reject.
-- affected rows = 1  ->  proceed to insert the ledger row, same transaction.
```

The check and the write were never separable. The balance update and the ledger
insert must be in the same database transaction — if the insert fails after the
balance moves, the ledger and the balance disagree and there is no way to tell
which is right.

---

## 8. Business rules enforced

The brief lists three. These are the nine actually implemented, all in
`services.py` and nowhere else.

1. Amounts are positive whole cents, and below a per-transaction ceiling of
   1,000,000.00 (100,000,000 cents).
2. A withdrawal may not exceed what is **available**, which is the balance minus
   whatever minimum the account type holds. Both types hold 0.00 at present, so
   available equals the balance; the service still never checks the account type
   to work this out — it asks the object.
3. Frozen accounts reject all customer-initiated movement. Admin adjustments are
   still allowed, because correcting an account is a normal reason to have frozen
   it.
4. Every balance change writes exactly one ledger entry. Always.
5. A resubmitted `clientTxnId` is rejected rather than applied twice.
6. A user may only touch their own accounts. Admins may read any.
7. Admins adjust by posting a ledger entry with a written reason of at least 10
   characters, never by setting a balance. Every admin action writes an audit row.
8. An opening balance is not a free gift — if non-zero it gets a ledger entry
   like any other credit, or reconciliation is broken before the account is a
   second old.
9. Registration cannot grant a role. `POST /api/auth/register` ignores a `role`
   field in the body, so nobody mints themselves an admin.

Rules 3 to 9 are not in the brief. They are cheap now and painful to retrofit.

---

## 9. Error handling: one table, one place

The service layer raises domain exceptions. `ERROR_STATUS` at the top of
[bank/api.py](bank/api.py) is the only place they become HTTP:

| Exception | Status | When |
| --- | --- | --- |
| `InvalidAmount` | **400** | Negative, zero, a float, a string, over the ceiling, not an int |
| `ValueError` / `TypeError` | **400** | Missing field, unknown account type, admin reason too short |
| *(no/invalid token)* | **401** | Missing, malformed, wrong signature, or expired — one message for all four |
| *(failed login)* | **401** | 401 means "authenticate"; 403 means "authenticating again will not help" |
| `NotAuthorized` | **403** | Authenticated, but lacks the role |
| `AccountNotFound` | **404** | No such account, **or** somebody else's account |
| `UserNotFound` | **404** | |
| `InsufficientFunds` | **409** | Overdraft, or past a savings minimum |
| `AccountNotActive` | **409** | Frozen |
| `DuplicateTransaction` | **409** | Replayed `clientTxnId` |
| `EmailAlreadyUsed` | **409** | Duplicate registration |
| *(unrecognised)* | **500** | Logged server-side, generic message to the client |

Order matters in that table: the lookup takes the first class the exception is an
instance of, so subclasses must come before their parents.

A wrong method on a real path returns **405**, not 404 — a POST to a GET-only URL
is a different mistake from a URL that does not exist, and saying so saves the
caller hunting for a typo that is not there.

---

## 10. Seed data

`python server.py` loads the cohort roster from
`seed_data_bank_app.md` (the planning document, not yet committed here): 14
users, 20 accounts, 73
transactions. Every password is `BankDemo123!`. Every email is on `example.com`,
which RFC 2606 reserves and which can never receive mail.

**The seed is replayed, not assigned.** Each account opens at zero and its ledger
is replayed through `BankService.deposit` and `.withdraw` — the same methods an
HTTP request reaches. That costs about half a second and buys three things:
reconciliation is true by construction; loading the seed is itself a test; and
the resulting balances are a genuine prediction, since every figure in the seed
document was computed independently. `seed.load()` asserts all twenty match.

Several balances break something on purpose and should not be tidied up:

| Account | Balance (cents) | Displays as | What it is for |
| --- | --- | --- | --- |
| 4 | `0` | `0.00` | Empty state, and a withdrawal against exactly zero |
| 6 | `1250` | `12.50` | Overdraft rejection — try to withdraw `1251` |
| 9 | `8421075` | `84,210.75` | Thousands separators and `tabular-nums` column alignment |
| 10 | `120000` **FROZEN** | `1,200.00` | Every deposit and withdrawal must be rejected |
| 11 | `123456` | `1,234.56` | `100010 + 23420 + 30 - 4`, which drifts to `1234.5599999999999` if done in float dollars |
| 18 | `1` | `0.01` | One cent: the smallest unit the system can express |

Accounts 9, 13 and 20 turned out to drift under float arithmetic as well, found
by accident while verifying the seed file rather than designed in. Four accounts
now detect a float in the chain rather than one. They cannot drift as integers,
but they are kept because the guard is against a future change that reintroduces
fractional arithmetic somewhere in the chain.

**Four names in the roster were derived from handles and are unconfirmed** (Ayan
Shabbir, Benjamin Voor, Bianca Alvarado, Justin Lin). Confirm them with their
owners before the demo, or use the handle as the display name.

---

## 11. Testing

```bash
python -m unittest -q        # 93 tests, ~5 seconds
MONGO_TESTS=1 python -m unittest -v        # with names, Mongo-enabled
python -m unittest test_bank # rules only, ~0.01 seconds
```

| Suite | Count | Covers |
| --- | --- | --- |
| `test_bank.py` | 34 | Business rules, called directly. Imports nothing HTTP. |
| `test_api.py` | 59 | Routing, auth, error mapping, serialization, password hashing, the seed, and one end-to-end pass over a real socket. |

Both suites assert `reconcile_all() == []` in `tearDown`, so the ledger invariant
is checked after every single test rather than in one test of its own.

Some tests exist to make a specific mistake fail loudly:

- `test_there_is_no_route_that_sets_a_balance` — scans the route table for
  anything with "balance" in the path.
- `test_there_is_no_way_for_an_admin_to_set_a_balance_directly` — asserts no
  `set_balance` method exists on the service or the account.
- `test_every_route_except_the_public_three_requires_a_token` — a new route added
  without `auth` fails here.
- `test_the_404_is_indistinguishable_from_a_missing_account` — asserts the two
  error messages are identical.
- `test_the_default_cost_is_high` — guards the PBKDF2 round count, since the test
  fixtures deliberately hash cheaply.

Fixtures hash at 1,000 PBKDF2 rounds instead of 600,000. At the production cost
this suite takes 12 seconds, and a suite slow enough to skip is a suite that gets
skipped. The round count lives inside each hash, so verification is unaffected,
and the test above guards the real default.

---

## 12. Design decisions worth defending in review

This is the Day 1 Module 2 material (methods, parameters, scope, overloading)
applied to the project rather than to exercises.

**Encapsulation.** `Account.balance` is a read-only property over `_balance`.
There is no setter, so `account.balance = 1000000` raises `AttributeError`. The
only path that changes a balance is `_apply`, called by the service layer
alongside a ledger entry. If `balance` were a public attribute, the invariant
`balance == sum(ledger)` would be unenforceable, because any line of code could
break it. There is a test asserting the setter does not exist.

**Inheritance at the point where the types can differ.** How much of a balance
may actually leave is a per-type rule, and it lives in an overridden
`minimum_balance` on `SavingsAccount`. `withdraw()` in `services.py` calls
`account.can_withdraw()` without ever checking the account type, so adding a
third account type means adding a class, not editing an `if`.

Worth being straight about the current state: `SavingsAccount.MINIMUM` is 0.00,
so the two types behave identically today and the override changes nothing an
observer could see. The claim being made here is about where the rule is written,
not about how much the two classes presently differ — the honest test of that is
that restoring a floor is a one-constant edit with no change to `withdraw`,
`transfer`, the serializers or the routes.

**Python has no method overloading.** That was question 2 of Module 2. Java
selects between same-named methods by parameter list at compile time; Python
binds one name to one function, so a second `def` of the same name replaces the
first. The Python equivalents are default arguments, `functools.singledispatch`,
and classmethods as named alternative constructors. `make_account()` is the
factory that does what an overloaded constructor would do in Java.

**Identity belongs to the repository.** `Account` objects arrive at
`store.add_account()` with `account_id = None` and leave with a number — that is
`AUTO_INCREMENT` made explicit. An earlier version numbered accounts from a
class-level counter on `Account`, which meant every account ever created in the
process shared one sequence and ids depended on how many other tests had run
first. Moving it into the store is what makes two `BankStore` instances genuinely
independent and what makes the seeded account numbers stable enough for the
Postman collection to reference.

**The Postman collection is generated.** `tools/export_postman.py` imports
`BankAPI` and walks the real route table. Hand-maintained, a collection drifts: a
route gets renamed, the collection keeps the old path, and the mismatch surfaces
during integration week instead of the afternoon it was introduced.

---

## 13. What is deliberately not done yet

| Not done | Why, and what it will touch |
| --- | --- |
| **A database** | **Done for MongoDB.** With `MONGODB_URI` and `MONGODB_DB` in `.env`, `python server.py` serves from Atlas and the data survives a restart; `--memory` is the way back. See [mongo.md](mongo.md). What is still open is only which database is *graded* — see section 14. |
| **A `seed.sql` for MySQL** | Written in `seed_data_bank_app.md` §3–4 but not extracted, and its amounts are in `DECIMAL`. If MySQL is chosen they become `BIGINT` cents — and §5, the MongoDB version, must not be run at all: it writes `Decimal128`, which this codebase refuses. |
| **A frontend** | **Scaffolded.** `frontend/` is a React + Vite app with routing, login, register, the account list and a typed-up API layer in `src/lib/api.js`; the remaining screens are stubs, one file each, waiting to be claimed. See [frontend/README.md](frontend/README.md). The API is CORS-enabled for a dev server on another port, and money is serialized as integer cents, so the client divides by 100 to display and never has to undo a float. |
| **httpOnly cookie sessions** | Tokens currently travel in an `Authorization` header, which a React client stores itself. A token in `localStorage` is readable by any injected script, so the cookie version is the better end state — it needs a real CSRF story and an exact-origin CORS policy, not `*`. |
| **Refresh tokens** | One week, then log in again. The long TTL is what stands in for a refresh lifecycle, and it is the wrong end state: a short token plus a refresh, and a session-timeout warning with an extend option (WCAG 2.2.1), belong with the frontend work. |
| **Rate limiting on login** | PBKDF2 makes each guess cost ~0.6s, which is real but not a substitute for lockout or backoff. |
| **The SQL script** | Already written and verified in the `seed_data_bank_app.md` planning document - section 3 (schema), section 4 (MySQL inserts), section 5 (MongoDB). Not yet extracted to a `.sql` file in this repo, because which database is graded is still open. |

### `http.server` is not a production server

It is in the standard library, which is what lets this run on a clean machine
with no virtualenv, and its own documentation says it is not for production. For
a training project graded on API correctness and layer separation that is fine.
Porting to FastAPI is mechanical and confined to `api.py`: the route table
becomes decorators, `_require_actor` becomes a dependency, and `ERROR_STATUS`
becomes an exception handler. Nothing outside that file moves.

---

## 14. Open questions for the instructor

These block the next phase, not this one.

1. **MySQL or MongoDB?** The brief says MySQL "to be confirmed"; the syllabus
   teaches MongoDB. Which will be graded? Keeping storage behind `store.py` is
   why the answer does not change anything in *this* submission — but it decides
   the schema, and on Mongo it decides whether the team needs a replica set
   (multi-document transactions require one; a standalone local `mongod` accepts
   the code and gives no atomicity, silently).

   **The MongoDB half of this is now built and settled.** We are on Atlas; a
   free M0 cluster *is* a three-node replica set, so every change runs inside a
   real transaction, and `test_mongo.py` proves it against the live cluster. See
   [mongo.md](mongo.md).

   What remains open is only which database is **graded**. `store.py` is why that
   answer costs us one class rather than the application: `MongoStore` answers the
   same method names, and `api.py`, `models.py` and `serializers.py` did not
   change when it landed. The repository interface did grow two members —
   `atomic()` and `save_balance()`/`save_status()` — which is the honest version
   of the claim and is written up in [mongo.md](mongo.md).
2. **Python or Spring Boot?** The brief allows both; the syllabus teaches Python.
3. **Is authentication core scope now?** The brief lists it as a bonus; the hiring
   manager asked for admin and user logins. This repo treats it as core.
4. **What should the admin be able to do?** Section 5 above is a proposal, not an
   answer. The brief does not define the persona at all.
5. **Is an immutable ledger acceptable,** or does the grading expect a simpler
   stored-balance model?
6. **Is deployment expected,** given Terraform and AWS appear in the syllabus, or
   is local sufficient?

---

## 15. Submission checklist

| Requirement | Status |
| --- | --- |
| **Source code (GitHub)** | This repository. `.env.example` committed, `.env` gitignored, no secrets. |
| **SQL script** | **Not in this repo yet.** Written and verified in the `seed_data_bank_app.md` planning document, §3–4 (MySQL) and §5 (MongoDB). Drop that document into `docs/` and extract the schema to `sql/schema.sql` once the database question is settled. |
| **Screenshots of UI** | Waiting on the frontend screens; the app itself runs (`cd frontend && npm run dev`). |
| **Postman collection** | [postman_collection.json](postman_collection.json) — 28 requests, generated from the route table, including a "Failure cases" folder covering overdraft, negative and malformed amounts, a frozen account, a replayed submission, and reading another user's account. |
