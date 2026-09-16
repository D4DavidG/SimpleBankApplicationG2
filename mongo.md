# MongoDB Atlas: setup for this project

How to get a working connection to our shared cloud database, and the reasoning
behind the choices so nobody has to re-litigate them mid-week.

Two audiences, two parts:

- **[Part A](#part-a-one-time-setup-one-person-only)** happens **once, by one person**, and is already done
  if someone has sent you an Atlas invite. Read it anyway — it is where the
  naming and access decisions are written down.
- **[Part B](#part-b-what-every-teammate-does)** is what **each of us does individually**, and takes about ten
  minutes.

Then **[verify](#verify-it-actually-works)** it works, because a connection string that looks right and a
connection string that *is* right are not distinguishable by eye.

> Atlas moves buttons around every few months. Where the wording below does not
> match what you see, the thing you are looking for is still named roughly the
> same — the left sidebar has **Database**, **Database Access**, and **Network
> Access**, and those three are the whole of the setup.

---

## Why Atlas, and not a local `mongod`

The syllabus teaches MongoDB and the brief says MySQL "to be confirmed", so the
storage question was open. Atlas settles the part of it that was actually
blocking us, for one specific reason:

**A free Atlas M0 cluster is a three-node replica set.** A local standalone
`mongod` is not. That matters more than it sounds like it does, because
**MongoDB multi-document transactions only work on a replica set** — and a
standalone `mongod` does not reject the transaction code, it just quietly gives
you no atomicity. You would find out during the demo.

We need multi-document transactions for exactly one thing, and it is the one
thing a bank cannot get wrong:

```
transfer():  debit source account
             credit target account      <- all four writes, or none of them
             insert TRANSFER_OUT ledger entry
             insert TRANSFER_IN  ledger entry
```

That is [`services.py`](bank/services.py) `transfer()`, whose docstring already
says "Both legs happen or neither does". In memory that is free, because nothing
can interrupt a Python method holding a lock. In a database it is free only if
the database can do transactions. So: Atlas.

The secondary reasons are ordinary ones. It is free, there is nothing to install
on five different machines, we all share one dataset so the frontend and backend
are not debugging against different data, and it survives a laptop being closed.

---

## The decisions, so we all make the same ones

| Thing | Our choice | Why |
| --- | --- | --- |
| Tier | **M0 (Free, Shared)** | 512 MB, never expires, no card required. Also a replica set — see above. |
| Provider / region | **Whichever is closest to most of us** | It is a latency decision and nothing else. Pick one and stop thinking about it. |
| Organization | `SimpleBankG2` | — |
| Project | `simple-bank` | Database users and IP access lists are **per project**, not per cluster. |
| Cluster | `Cluster0` (the default) | Renaming it means editing everyone's connection string for no gain. M0 allows one cluster per project. |
| Database users | **One per teammate**, not one shared login | Revocable individually, and the Atlas access logs then say *who* did the thing. Costs nothing. |
| Databases | `simple_bank` shared, `simple_bank_<yourname>` each, `simple_bank_test` for the suite | See [Which database you write to](#which-database-you-write-to). |
| Collections | `users`, `accounts`, `transactions`, `counters` | Mirrors the three tables in the brief, plus one for id allocation. |
| Network access | `0.0.0.0/0` for the duration of the project | A deliberate trade-off, argued in [Network access](#network-access-and-the-00000-decision). |

---

## Part A: one-time setup (one person only)

If you have been invited to an existing project, skip to [Part B](#part-b-what-every-teammate-does).

### A1. Create the account and the cluster

1. Go to **[cloud.mongodb.com](https://cloud.mongodb.com)** and sign up. Google
   sign-in is fine and is one less password.
2. Atlas asks a few onboarding questions (what are you building, what language).
   The answers change nothing but the tips it shows you. Python / Learning MongoDB.
3. On the deploy screen choose **M0 / Free**. This is the one screen where it is
   genuinely easy to click the wrong thing — the paid tiers are presented first
   and more attractively, and one of them is preselected. **M0** is the free one.
   **No credit card is required for M0.** If you are being asked for a card, you
   have selected a paid tier.
4. Provider and region: pick the region closest to most of the team. AWS is the
   default and there is no reason to change it.
5. Cluster name: leave it as **`Cluster0`**.
6. **Create**. Provisioning takes one to three minutes.

### A2. Name the organization and project

Atlas will have invented names like "My Org 2026-09-16" and "Project 0". Rename
them, because five people are about to be looking at this:

- **Organization Settings** → rename to `SimpleBankG2`
- **Project Settings** → rename to `simple-bank`

### A3. Network access

Left sidebar → **Network Access** → **Add IP Address** → **Allow access from
anywhere** (`0.0.0.0/0`) → **Confirm**.

Read [Network access](#network-access-and-the-00000-decision) before doing this so it is a decision and not a
default. The short version: the alternative breaks for a teammate every time
their IP changes, which on campus wifi is roughly daily.

### A4. Invite the team

**Project Access** (under Access Manager) → **Invite to Project**. Add each
teammate's email with the role **Project Data Access Read/Write**.

Not **Project Owner** — an owner can delete the cluster, and there is no undo and
no backup on M0. One owner is enough.

Each teammate creates **their own database user** in Part B. Do not create users
for them and do not send passwords around Slack.

### A5. Tell the team

Post the organization name, the project name, and a link to this file. That is
all anyone needs — everything else they generate themselves.

---

## Part B: what every teammate does

### B1. Accept the invite

Check your email for the Atlas invitation, accept it, and create your MongoDB
account if you do not have one. You should land in the `simple-bank` project and
see `Cluster0`.

### B2. Create your own database user

Left sidebar → **Database Access** → **Add New Database User**.

- **Authentication Method:** Password
- **Username:** your first name, lowercase, no spaces — `david`, `aaron`
- **Password:** click **Autogenerate Secure Password**, then **Copy**.

  Use the autogenerated one. Not because you cannot invent a password, but
  because the connection string is a URL, and a password containing `@ : / ? # [ ]`
  has to be percent-encoded before it can go in one. Atlas generates
  alphanumeric passwords, which sidesteps that entirely. (If you insist on your
  own: `python -c "from urllib.parse import quote_plus; print(quote_plus('your password'))"`.)

- **Database User Privileges:** **Read and write to any database**.
- **Add User**.

**Paste the password somewhere now.** Atlas will not show it to you again, and
the recovery path is deleting the user and making a new one.

### B3. Get your connection string

**Database** → **Connect** on `Cluster0` → **Drivers** → Driver **Python**.

**Ignore the version dropdown, and ignore the `pip install` line on that page.**
Take *only* the connection string from step 3 of it. Why, in detail, is the next
section — it is the single easiest way to break your setup, and the page hands it
to you looking official.

Copy the string. It looks like:

```
mongodb+srv://david:<db_password>@cluster0.ab1cd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
```

Replace `<db_password>` — angle brackets and all — with the password from B2.

The `+srv` matters: it is a DNS-based lookup that finds all three replica set
nodes from one hostname. It is why the string has no port number in it, and it
is why `dnspython` is a dependency.

### B4. Install the driver

```bash
pip install -r requirements.txt
```

**That is the whole step. Do not run the command Atlas shows you.**

This is worth being blunt about, because the Atlas "Connect" page displays an
install line that is actively wrong for us, and it looks like the authoritative
instruction on an official page. It currently reads:

```
python -m pip install "pymongo[srv]==3.12"     # <- do NOT run this
```

Two separate problems, either of which costs you an afternoon:

**The "3.12" is the pymongo driver version, not your Python version.** It is
natural to read it as Python 3.12 and think it is a minimum. It is not: it is an
exact pin (`==`) to **pymongo 3.12.0, released in 2021**, four major versions
behind the current 4.18. Running it on Python 3.14 downloads a source tarball
rather than a wheel — there is no cp314 build of a 2021 release — so pip tries to
compile the C extensions locally, and it downgrades `dnspython` from 2.8 to 1.16
on the way past. The version dropdown on that page changes only this sample line;
the connection string above it is the same either way, which is why you can
safely ignore the dropdown entirely.

**The `[srv]` extra no longer exists.** Every Atlas tutorial still says it. As of
pymongo 4.18 pip prints `WARNING: pymongo 4.18.1 does not provide the extra
'srv'` and carries on. That one is harmless, and also unnecessary — `dnspython`
is a hard dependency of modern pymongo, so plain `pymongo` already speaks
`mongodb+srv://`.

`requirements.txt` pins `pymongo>=4.18.1,<5`, which has a real cp314 wheel and
installs in seconds. Use it and move on.

This is the first third-party package this project has ever needed. Everything
up to now has been standard library, which is why there was no `requirements.txt`
until this file existed. A virtual environment is now worth having:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

`.venv/` is already gitignored.

### B5. Put it in `.env`

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

Open `.env` and set:

```bash
MONGODB_URI=mongodb+srv://david:YourActualPassword@cluster0.ab1cd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0
MONGODB_DB=simple_bank_david
```

No quotes, no spaces around the `=`.

**`.env` is gitignored and must stay that way.** `.env.example` is the committed
one and it never contains a real password. Check before every commit: if
`git status` ever lists `.env`, stop and work out why the ignore rule stopped
matching.

> **Heads up for whoever writes the store:** nothing in this repo reads `.env`
> yet. `security.py` reads `os.environ` directly, so `.env` is currently
> documentation rather than configuration. `tools/check_mongo.py` parses it
> itself so that this tutorial is true today; the real loader is a decision for
> the store work, and it is about fifteen lines of standard library — we do not
> need `python-dotenv` for `KEY=value`.

---

## Verify it actually works

```bash
python tools/check_mongo.py
```

This is not a formality. It runs seven checks, and each one fails in a way you
would otherwise spend an afternoon on:

| # | Check | What a failure means |
| --- | --- | --- |
| 1 | `pymongo` imports | You installed into a different Python than you are running |
| 2 | `MONGODB_URI` is set and parses | Placeholder left in, or an unencoded password |
| 3 | DNS resolves the `+srv` hostname | Cluster name typo, or a network blocking DNS SRV records |
| 4 | Server responds to a ping | **Your IP is not on the access list** — much the most common |
| 5 | Credentials are accepted | Wrong password, or you edited the user after copying the string |
| 6 | Insert / read / delete round-trips | Your user does not have readWrite |
| 7 | **A multi-document transaction commits** | You are not on a replica set — `transfer()` would silently not be atomic |

Check 7 is the one that justifies all of this. It writes to two documents inside
one transaction and rolls it back, which proves the guarantee `transfer()` needs
rather than assuming it from the tier name.

Everything the script writes goes to a `_connection_check` collection and is
deleted afterwards. It never touches `users`, `accounts`, or `transactions`.

Expected output ends with:

```
All checks passed. Atlas is ready.
```

---

## Which database you write to

One cluster, several databases. `MONGODB_DB` in your `.env` decides which one you
are pointed at.

| Database | Used by | Why separate |
| --- | --- | --- |
| `simple_bank` | The demo, and the frontend | One known-good dataset everyone shows |
| `simple_bank_<yourname>` | Your day-to-day development | So your reseed does not delete the data someone is demoing |
| `simple_bank_test` | The test suite | It gets wiped constantly. It must never be a database anyone cares about |

On M0 this costs nothing — the 512 MB is shared across all of them and our entire
seeded dataset is a few hundred kilobytes. Creating a database in MongoDB is not
an operation you perform; writing to a name that does not exist creates it.

**Default yourself to `simple_bank_<yourname>`.** Switch to `simple_bank` only
when you deliberately want the shared data.

---

## How this fits the code

It fits in one file, which was the entire point of writing it the way it is
written. [`store.py`](bank/store.py) says so in its own docstring:

> When MySQL or MongoDB arrives later in the week, this file is the only one that
> gets rewritten and the business rules in `services.py` do not change at all.

So the work is a `MongoStore` class with the same method names as `BankStore` —
`add_user`, `get_account`, `add_transaction`, `ledger_sum`, and the rest — and
one changed line in `server.py` choosing between them. `services.py`, `api.py`,
`models.py` and the tests do not move.

Four things transfer from the in-memory version to Mongo, and they are the four
places where "it still works" and "it is still correct" come apart:

| In memory today | In Mongo | Note for whoever writes it |
| --- | --- | --- |
| `itertools.count(1)` for ids | A `counters` collection with `find_one_and_update` / `$inc` | Mongo's `_id` is an ObjectId; the brief's API returns integer ids, so we keep integers and allocate them atomically |
| `_email_index` dict | A **unique index** on `users.email` | `db.users.create_index("email", unique=True)` — then the duplicate-email check is the index, not Python |
| `_client_txn_ids` set | A **unique index** on `transactions.client_txn_id` (sparse) | This is the idempotency guarantee. A set in one process does not survive two processes; the index does |
| `threading.RLock()` | A **transaction** in `transfer()` | The reason we are on Atlas rather than a local `mongod` |

Money stays as integer cents. BSON has a 64-bit integer type and Python's `int`
maps to it — do **not** let it become a `Double` on the way in, which is the same
float problem [`money.py`](bank/money.py) exists to prevent, arriving by a
different door.

---

## Network access, and the `0.0.0.0/0` decision

`0.0.0.0/0` means "accept connections from any IP address on the internet". That
is not a thing to do casually, so here is the actual argument.

**The alternative is worse in practice.** The secure option is listing each
teammate's IP. Home broadband IPs rotate, campus and café wifi give you a
different address every time you connect, and a phone hotspot is different again.
Every one of those changes produces the same symptom — a connection that hung and
then timed out, with an error message that does not say "your IP changed" — and
the fix requires whoever owns the project to be awake. Across five people for a
week, that failure happens repeatedly, and the usual response to it is a rushed
`0.0.0.0/0` at 11pm with nobody thinking about it.

**What actually protects the cluster is the credentials, not the IP list.** An
attacker reaching the open port still needs a valid database username and
password. The IP list is defence in depth — a real and useful layer, but the
second one.

**And the data is not real.** Fourteen invented users, invented balances, one
shared demo password that is printed on the server's own startup banner. There is
nothing in this cluster to steal.

So the trade is: a meaningful loss of a secondary control, against a primary
control that stays intact, protecting data that does not matter, in exchange for
the week not containing a recurring self-inflicted outage. For this project that
is the right trade. **In production it is not**, and it is worth being able to
say why in a review: production uses VPC peering or private endpoints so the
database has no public IP at all.

What still has to hold, given the above:

- **Every teammate has their own database user.** One shared credential plus an
  open IP list is genuinely careless — nothing is revocable and nothing is
  attributable.
- **No real data. Ever.** Not a real email, not a real name, not a password
  anyone uses elsewhere.
- **The connection string never enters git.** It contains the credential that is
  now the only thing standing there.

---

## When it does not work

Atlas failures are unhelpfully worded. Here is the translation table.

### `ServerSelectionTimeoutError` after ~30 seconds

Nine times in ten: **your IP is not on the access list.** Atlas does not refuse
the connection, it drops it, so the client waits and then gives up — which is
why the message says "timeout" rather than "not allowed".

→ **Network Access** → confirm there is a `0.0.0.0/0` entry and it says
**Active**, not **Pending**. A new entry takes a minute or two to apply.

Otherwise: the cluster is **paused** (M0 pauses after 60 days idle — the
**Database** page has a **Resume** button), or a school or corporate network is
blocking outbound port 27017.

### `Authentication failed`

The username or password in the string is wrong. Most often the literal
`<db_password>` placeholder is still in there, angle brackets and all, or a
password with symbols in it went in unencoded.

→ Fastest fix: **Database Access** → **Edit** your user → **Edit Password** →
**Autogenerate** → copy → update `.env`. Do not spend twenty minutes on it.

Also check you are connecting as a **database user** (Database Access) and not
with your Atlas *account* login. They are unrelated credentials with confusingly
similar names.

### `ConfigurationError: The "dnspython" module must be installed`

pymongo cannot resolve `mongodb+srv://`.

→ `pip install -r requirements.txt`, in the environment you are actually running.
If you have a venv, is it activated? `python -c "import sys; print(sys.prefix)"`
should be inside your project, not `C:\Python314`.

### `InvalidURI: Invalid URI scheme` or the string looks mangled

Something reformatted the connection string — a quote, a trailing space, a line
break from copying out of a chat message.

→ Repaste it as one line, no surrounding quotes.

### `ModuleNotFoundError: No module named 'pymongo'` right after installing it

Or: check 1 passes but the API is unrecognisable, or pip spent minutes trying to
compile something.

You probably ran the install line from the Atlas Connect page, which pins
**pymongo 3.12 from 2021** and downgrades `dnspython`. See [B4](#b4-install-the-driver).

→ Undo it:

```bash
pip uninstall -y pymongo dnspython
pip install -r requirements.txt
python tools/check_mongo.py
```

Check 1 prints the version it actually found. It should say **4.18.1 or later**.

### `OperationFailure: user is not allowed to do action`

Your database user was created read-only.

→ **Database Access** → **Edit** → **Read and write to any database**.

### Check 7 fails but everything else passes

You are connected to a standalone `mongod`, not Atlas — check `MONGODB_URI`
actually points at `mongodb+srv://...mongodb.net` and not `localhost:27017`.
This is the failure worth caring about: everything would appear to work, and
`transfer()` would be non-atomic without ever saying so.

---

## Notes for later

- **M0 allows 500 concurrent connections.** pymongo opens a pool of up to 100 per
  `MongoClient` by default. Five of us running servers is fine; five of us each
  constructing a client per request is not. Construct **one** `MongoClient` at
  startup and share it — it is thread-safe and designed to be reused.
- **M0 pauses after 60 days of no activity.** The data survives; you press Resume.
- **There are no backups on M0.** Our dataset is regenerated by `seed.py` in a
  second, so this is fine — but it is why only one person is Project Owner.
- **Reads can be stale.** M0 is three nodes, and the default read preference is
  `primary`, so this does not affect us. It would if anyone sets
  `readPreference=secondary` to be clever. Do not.

## Open questions this settles, and one it does not

Settled: README §14 question 1 asked whether Mongo would need a replica set for
transactions. It does, and Atlas M0 provides one, and `tools/check_mongo.py`
proves it per-machine rather than taking the tier documentation's word for it.

Not settled: whether we are being **graded** on MySQL or MongoDB. The brief says
MySQL "to be confirmed" and the syllabus teaches Mongo. Atlas being set up does
not answer that — it just means the Mongo path is no longer blocked. The reason
this is survivable is `store.py`: if the answer comes back MySQL, what we lose is
this file and one class, not the application.
