"""Demo data: the cohort roster from `seed_data_bank_app.md`, in Python.

WHY REPLAY INSTEAD OF ASSIGN
---------------------------
The obvious way to seed is to set each balance to its final figure and insert the
ledger rows next to it. This module does not do that. It opens each account at
zero and then replays its transactions through `BankService.deposit` and
`.withdraw` - the same methods an HTTP request reaches.

That costs a few milliseconds and buys three things:

  1. Reconciliation is true by construction. There is no path here that can move
     a balance without writing the matching entry, because there is no path here
     that touches a balance at all.
  2. Loading the seed is itself a test. If a rule is broken, seeding raises
     instead of quietly producing a database that disagrees with the code.
  3. The resulting balances are a genuine prediction. Every figure in the seed
     document was computed independently; if replaying the same ledger through
     this codebase produces those exact numbers, the arithmetic agrees. The check
     at the bottom of this file asserts precisely that.

WHAT THE NUMBERS ARE FOR
------------------------
Several balances are chosen to break something on purpose, and they should not be
tidied up. The seed document explains each one; the short version:

    account  4   0.00        empty state, and a withdrawal against exactly zero
    account  6   12.50       overdraft rejection: try to withdraw 12.51
    account  9   84,210.75   thousands separators and tabular-nums alignment
    account 10   FROZEN      every deposit and withdrawal must be rejected
    account 11   1,234.56    built from 1000.10 + 234.20 + 0.30 - 0.04, which
                             drifts to 1234.5599999999999 in IEEE 754
    account 18   0.01        one cent: rounding and truncation in display code

Accounts 9, 13 and 20 turned out to drift under float arithmetic too, which was
found by accident while verifying the seed file rather than designed in.

PASSWORDS AND EMAILS
--------------------
Every seeded user has the password `BankDemo123!`. That is fine for a demo and
only for a demo. Every address is on `example.com`, which RFC 2606 reserves for
exactly this and which can never receive mail - no real address belongs in a file
that ends up in a public repository.
"""
from decimal import Decimal

from .models import ROLE_ADMIN
from .security import hash_password

# The shared demo password. Hashed on the way in by `register_user`; the
# plaintext exists here, in the demo seed, and nowhere else.
DEMO_PASSWORD = "BankDemo123!"

# (name, email, role). Order fixes the user ids, 1 to 14.
#
# Four names in the source roster were derived from handles and are unconfirmed
# (Ayan Shabbir, Benjamin Voor, Bianca Alvarado, Justin Lin). Confirm them with
# their owners before the demo, or use the handle as the display name.
USERS = [
    ("Aaron Forrester",   "aaron.forrester@example.com",   "CUSTOMER"),
    ("Alexander Melendez", "alexander.melendez@example.com", "CUSTOMER"),
    ("Alisa Katsionova",  "alisa.katsionova@example.com",  "CUSTOMER"),
    ("Ayan Shabbir",      "ayan.shabbir@example.com",      "CUSTOMER"),
    ("Benjamin Voor",     "benjamin.voor@example.com",     "CUSTOMER"),
    ("Bianca Alvarado",   "bianca.alvarado@example.com",   ROLE_ADMIN),
    ("Daniel Tran",       "daniel.tran@example.com",       "CUSTOMER"),
    ("David Gusmao",      "david.gusmao@example.com",      ROLE_ADMIN),
    ("Erik Mayes",        "erik.mayes@example.com",        "CUSTOMER"),
    ("Justin Lin",        "justin.lin@example.com",        "CUSTOMER"),
    ("Paul Bobev",        "paul.bobev@example.com",        "CUSTOMER"),
    ("Sean Cook",         "sean.cook@example.com",         "CUSTOMER"),
    ("Shraeyas Muthaiah", "shraeyas.muthaiah@example.com", "CUSTOMER"),
    ("Sonia Jain",        "sonia.jain@example.com",        "CUSTOMER"),
]

# (owner user id, account type, freeze after seeding?). Order fixes account ids 1-20.
ACCOUNTS = [
    (1, "CHECKING", False), (1, "SAVINGS", False),
    (2, "CHECKING", False),
    (3, "CHECKING", False), (3, "SAVINGS", False),
    (4, "CHECKING", False),
    (5, "CHECKING", False),
    (6, "CHECKING", False),
    (7, "CHECKING", False), (7, "SAVINGS", True),     # account 10 ends up FROZEN
    (8, "CHECKING", False), (8, "SAVINGS", False),
    (9, "CHECKING", False),
    (10, "CHECKING", False),
    (11, "CHECKING", False),
    (12, "CHECKING", False),
    (13, "CHECKING", False), (13, "SAVINGS", False),
    (14, "CHECKING", False), (14, "SAVINGS", False),
]

# (account id, "D" deposit or "W" withdrawal, amount). Amounts are strings, never
# floats - that is the whole point of the exercise and it starts at the data.
LEDGER = [
    (1, "D", "3968.00"), (1, "W", "491.04"), (1, "W", "431.52"), (1, "W", "297.60"), (1, "W", "267.84"),
    (2, "D", "25200.00"), (2, "W", "1795.50"), (2, "W", "567.00"), (2, "W", "7087.50"),
    (3, "D", "1459.74"), (3, "W", "10.95"), (3, "W", "405.08"), (3, "W", "76.64"), (3, "W", "54.73"),
    (4, "D", "250.00"), (4, "W", "250.00"),
    (5, "D", "6880.00"), (5, "W", "748.20"), (5, "W", "1831.80"),
    (6, "D", "12.50"),
    (7, "D", "5880.32"), (7, "W", "661.54"), (7, "W", "264.61"), (7, "W", "1278.97"),
    (8, "D", "800.00"), (8, "W", "51.00"), (8, "W", "249.00"),
    (9, "D", "134737.20"), (9, "W", "21726.37"), (9, "W", "2021.06"), (9, "W", "10610.55"), (9, "W", "16168.47"),
    (10, "D", "1920.00"), (10, "W", "79.20"), (10, "W", "72.00"), (10, "W", "165.60"), (10, "W", "403.20"),
    (11, "D", "1000.10"), (11, "D", "234.20"), (11, "D", "0.30"), (11, "W", "0.04"),
    (12, "D", "32000.00"), (12, "W", "3360.00"), (12, "W", "6720.00"), (12, "W", "1920.00"),
    (13, "D", "1193.58"), (13, "W", "317.79"), (13, "W", "129.80"),
    (14, "D", "9680.00"), (14, "W", "1270.50"), (14, "W", "1016.40"), (14, "W", "1343.10"),
    (15, "D", "204.91"), (15, "W", "16.14"), (15, "W", "60.70"),
    (16, "D", "15999.98"), (16, "W", "3419.99"), (16, "W", "240.00"), (16, "W", "240.00"), (16, "W", "2100.00"),
    (17, "D", "496.72"), (17, "W", "72.65"), (17, "W", "54.02"), (17, "W", "55.88"), (17, "W", "3.72"),
    (18, "D", "0.01"),
    (19, "D", "8448.00"), (19, "W", "1077.12"), (19, "W", "696.96"), (19, "W", "1393.92"),
    (20, "D", "115.36"), (20, "W", "39.80"), (20, "W", "3.46"),
]

# The balances the seed document states, computed there with Python's Decimal and
# entirely independently of this codebase. Replaying LEDGER must reproduce them.
EXPECTED_BALANCES = {
    1: "2480.00", 2: "15750.00", 3: "912.34", 4: "0.00", 5: "4300.00",
    6: "12.50", 7: "3675.20", 8: "500.00", 9: "84210.75", 10: "1200.00",
    11: "1234.56", 12: "20000.00", 13: "745.99", 14: "6050.00", 15: "128.07",
    16: "9999.99", 17: "310.45", 18: "0.01", 19: "5280.00", 20: "72.10",
}

FREEZE_REASON = "Seeded frozen for the freeze/unfreeze demo path"


def load(service, password: str = DEMO_PASSWORD, verify: bool = True) -> dict:
    """Populate an empty store. Returns a summary for the caller to print.

    Expects a store with nothing in it: ids are positional, so seeding twice
    produces users 15 to 28 and the account numbers stop matching the document.
    """
    if service.store.all_users():
        raise RuntimeError("seed.load() expects an empty store")

    # --- users -----------------------------------------------------------
    # Hash the shared demo password ONCE and reuse it for all fourteen rows.
    # PBKDF2 at 600,000 rounds costs about 0.6 seconds on purpose, so hashing per
    # user would put nine seconds on every server start for no security benefit:
    # the password is identical and published in this file either way. The SQL
    # seed script does the same thing with one bcrypt hash.
    #
    # This is a demo shortcut and nothing else. Real registration goes through
    # `register_user(password=...)`, which salts each user separately.
    shared_hash = hash_password(password)
    users = {}
    for name, email, role in USERS:
        user = service.register_user(name, email, role=role,
                                     password_hash=shared_hash)
        users[user.user_id] = user

    # --- accounts, opened at zero ----------------------------------------
    # Opening balance stays 0.00 deliberately. Every cent arrives as a ledger
    # entry below, so there is no "where did this money come from" gap.
    accounts = {}
    to_freeze = []
    for owner_id, account_type, freeze in ACCOUNTS:
        account = service.open_account(users[owner_id], account_type)
        accounts[account.account_id] = account
        if freeze:
            to_freeze.append(account.account_id)

    # --- ledger, replayed through the real rules --------------------------
    # Each entry carries the same client_txn_id as the SQL seed, which also
    # populates the idempotency index: resubmitting "seed-0001-01" is refused.
    admin = next(u for u in users.values() if u.is_admin)
    for index, (account_id, direction, amount) in enumerate(LEDGER, start=1):
        account = accounts[account_id]
        actor = users[account.user_id]
        client_txn_id = f"seed-{index:04d}-{account_id:02d}"
        if direction == "D":
            service.deposit(account_id, amount, actor, client_txn_id)
        else:
            service.withdraw(account_id, amount, actor, client_txn_id)

    # --- freeze last -------------------------------------------------------
    # After the replay, not before: a frozen account rejects movement, which is
    # exactly the rule that would stop its own ledger from loading.
    for account_id in to_freeze:
        service.set_frozen(account_id, True, FREEZE_REASON, admin)

    if verify:
        _verify(service)

    return {
        "users": len(users),
        "accounts": len(accounts),
        "transactions": len(LEDGER),
        "password": password,
        "admins": [u.email for u in users.values() if u.is_admin],
    }


def _verify(service) -> None:
    """Two assertions that make loading the seed a test rather than a fixture."""
    # 1. Every balance matches the figure computed independently in the seed doc.
    for account_id, expected in EXPECTED_BALANCES.items():
        actual = service.store.get_account(account_id).balance
        if actual != Decimal(expected):
            raise AssertionError(
                f"account {account_id}: expected {expected}, replayed to {actual}"
            )
    # 2. Every stored balance still equals the sum of its own ledger.
    broken = service.reconcile_all()
    if broken:
        raise AssertionError(f"seeded data does not reconcile: {broken}")
