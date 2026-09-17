"""Live traffic against MongoDB Atlas, paced so you can watch it arrive.

    python simulate.py                      # runs until Ctrl+C, ~2s per action
    python simulate.py --reset              # start from an empty database
    python simulate.py --steps 40           # stop after 40 actions
    python simulate.py --delay 5            # slower, for narrating
    python simulate.py --fast               # no delay, for filling a database

Open the Atlas Data Explorer in a browser next to this terminal:

    cloud.mongodb.com -> Clusters -> Cluster0 -> Browse Collections

Pick the database named in the banner below, click a collection, and press the
refresh icon after each action. **Atlas does not refresh by itself** - the data
is arriving whether or not the page is showing it, and that is the single most
confusing thing about watching a database in a browser.

Every line printed names the collection and the `_id` that changed, so you can
find the exact document the line is talking about.

WHY THIS EXISTS AS WELL AS console.py
-------------------------------------
`console.py` is for typing values in yourself. This is for the other half of a
demo: something has to be happening continuously while you talk, and clicking
refresh on a database nobody is writing to proves nothing.

It generates ordinary banking activity - people open accounts, deposit wages,
withdraw cash, send each other money, and occasionally an admin freezes
something. It goes through `BankService`, which is the same path the REST API
takes, so nothing here can succeed that the API would refuse.

REFUSALS ARE PART OF THE SIMULATION
-----------------------------------
Withdrawals are deliberately sized to overdraw sometimes, and roughly one
submission in twelve is sent twice with the same reference id. Those are printed
as refusals and nothing is written - which is the interesting thing to catch on
screen, because the database is where a missing rule would show up as a balance
that should not exist.
"""
import argparse
import itertools
import os
import random
import sys
import time
from datetime import datetime

from bank import (
    BankError, BankService, InsufficientFunds, format_money,
)

FIRST = ["Ada", "Bram", "Cleo", "Dev", "Esme", "Femi", "Gita", "Hugo", "Ines",
         "Jonas", "Kira", "Luca", "Mara", "Niko", "Orla", "Pia", "Quinn", "Rosa",
         "Sami", "Tova", "Uma", "Vero", "Wren", "Yara", "Zane"]
LAST = ["Abara", "Bianchi", "Costa", "Dahl", "Ekwueme", "Fontaine", "Grimaldi",
        "Haugen", "Ivarsson", "Jansen", "Keita", "Lindqvist", "Moreau", "Nayar",
        "Okafor", "Petrov", "Rios", "Sorensen", "Takahashi", "Varga"]

REASONS = [
    "Reversing a fee misposted on the account",
    "Correcting a duplicated card settlement",
    "Suspected card compromise, under review",
    "Review complete, no fraud found",
    "Goodwill credit agreed with the customer",
]


def now():
    return datetime.now().strftime("%H:%M:%S")


class Sim:
    """Generates activity and narrates what it wrote."""

    def __init__(self, svc, store, rng):
        self.svc = svc
        self.store = store
        self.rng = rng
        self.admin = None
        self.customers = []
        self.accounts = []          # (account_id, owner)
        self.used_refs = []
        self.counter = itertools.count(1)
        self._name_pool = []
        # A token unique to this run, mixed into every generated email address.
        # Without it, a second run against a database that was not --reset would
        # number its people from 1 again and eventually collide with somebody
        # already registered - the duplicate-email rule firing correctly, and
        # stopping the simulation for a reason nobody watching would guess.
        self.run_tag = f"{int(time.time()) % 100000:05d}"
        self.stats = {"written": 0, "refused": 0}

    # ---- output ----

    def wrote(self, collection, doc_id, text):
        self.stats["written"] += 1
        print(f"  {now()}  [{collection:<12} _id={doc_id!s:<4}] {text}")

    def refused(self, exc, text):
        """A rule stopped it, so nothing reached the database.

        Printed in the same column as a write, with no id, because the point is
        that there is no document to go and look at.
        """
        self.stats["refused"] += 1
        print(f"  {now()}  [{'REFUSED':<12} --------] {text}")
        print(f"{'':35}-> {type(exc).__name__}: {exc}")

    # ---- setting the scene ----

    def ensure_cast(self, password_hash):
        """Make sure there is an admin and at least a few customers to act on.

        Users are created with a pre-computed hash rather than a password.
        Deriving one costs about 0.6 seconds by design, and a simulation that
        spent that on every new customer would be watching PBKDF2 rather than
        MongoDB. `seed.py` does the same thing for the same reason.
        """
        existing = self.store.all_users()
        for user in existing:
            (self.customers if not user.is_admin else []).append(user)
            if user.is_admin and self.admin is None:
                self.admin = user

        if self.admin is None:
            self.admin = self.svc.register_user(
                "Sim Admin", "sim.admin@example.com", role="ADMIN",
                password_hash=password_hash)
            self.wrote("users", self.admin.user_id, "admin created: Sim Admin")

        for account in self.store.all_accounts():
            owner = next((u for u in self.customers if u.user_id == account.user_id), None)
            if owner is not None:
                self.accounts.append((account.account_id, owner))

        while len(self.customers) < 3:
            self.new_customer(password_hash)

    # ---- actions ----

    def new_customer(self, password_hash):
        # Drawn from a shuffled pool rather than chosen independently each time:
        # with replacement, a short run happily invents four different people
        # who all share a first name, and that reads as a bug in the demo.
        if not self._name_pool:
            self._name_pool = [f"{f} {l}" for f in FIRST for l in LAST]
            self.rng.shuffle(self._name_pool)
        name = self._name_pool.pop()
        n = next(self.counter)
        email = f"{name.lower().replace(' ', '.')}.{self.run_tag}{n}@example.com"
        user = self.svc.register_user(name, email, password_hash=password_hash)
        self.customers.append(user)
        self.wrote("users", user.user_id, f"registered {name} <{email}>")

        kind = self.rng.choice(["CHECKING", "SAVINGS"])
        opening = self.rng.randrange(2_500, 250_000, 500)
        account = self.svc.open_account(user, kind, opening)
        self.accounts.append((account.account_id, user))
        self.wrote("accounts", account.account_id,
                   f"opened {kind} for {name}, {format_money(account.balance)}")
        # open_account does not hand back the ledger entry it posted, and a
        # placeholder id would be useless for finding the document in Atlas -
        # so read back the newest entry on the account, which is that one.
        rows = self.store.transactions_for_account(account.account_id)
        if rows:
            self.wrote("transactions", rows[0].txn_id,
                       "opening balance posted as a ledger entry, not assigned")

    def deposit(self):
        account_id, owner = self.rng.choice(self.accounts)
        amount = self.rng.randrange(1_000, 180_000, 100)
        # Roughly one in twelve is a resubmission of a reference already used -
        # the double-clicked submit button. The unique index refuses it.
        if self.used_refs and self.rng.random() < 1 / 12:
            # The last one, not a random one: a double-clicked submit button
            # resends what was just sent. Popping it means the same reference is
            # not replayed again and again, which looks like a stuck loop.
            ref = self.used_refs.pop()
            try:
                self.svc.deposit(account_id, amount, owner, client_txn_id=ref)
                print("  !! a replayed reference was accepted. That is a bug.")
            except BankError as exc:
                self.refused(exc, f"{owner.name} resubmitted reference {ref}")
            return

        ref = f"sim-{next(self.counter):05d}"
        try:
            txn = self.svc.deposit(account_id, amount, owner, client_txn_id=ref)
        except BankError as exc:
            # Most often the account was frozen by an admin action a few steps
            # ago. A deposit into a frozen account is refused like any other
            # movement, and the simulation has to survive it: an unguarded call
            # here ends the run at the least convenient moment, which is while
            # somebody is watching.
            self.refused(exc, f"{owner.name} tried to deposit "
                              f"{format_money(amount)} to #{account_id}")
            return
        self.used_refs.append(ref)
        balance = self.svc.get_account_for(account_id, owner).balance
        self.wrote("transactions", txn.txn_id,
                   f"{owner.name} deposited {format_money(amount)} to #{account_id}"
                   f"  -> {format_money(balance)}")

    def withdraw(self):
        account_id, owner = self.rng.choice(self.accounts)
        balance = self.svc.get_account_for(account_id, owner).balance
        # Sized to overdraw sometimes on purpose: a simulation in which nothing
        # is ever refused does not show that anything is being enforced.
        amount = self.rng.randrange(1_000, max(2_000, int(balance * 1.4)), 100)
        try:
            txn = self.svc.withdraw(account_id, amount, owner)
        except InsufficientFunds as exc:
            self.refused(exc, f"{owner.name} tried to withdraw "
                              f"{format_money(amount)} from #{account_id}")
            return
        except BankError as exc:
            self.refused(exc, f"{owner.name} tried to withdraw from #{account_id}")
            return
        after = self.svc.get_account_for(account_id, owner).balance
        self.wrote("transactions", txn.txn_id,
                   f"{owner.name} withdrew {format_money(amount)} from #{account_id}"
                   f"  -> {format_money(after)}")

    def transfer(self):
        if len(self.accounts) < 2:
            return self.deposit()
        (src, owner), (dst, _) = self.rng.sample(self.accounts, 2)
        amount = self.rng.randrange(500, 60_000, 100)
        try:
            out, _ = self.svc.transfer(src, dst, amount, owner)
        except BankError as exc:
            self.refused(exc, f"{owner.name} tried to send "
                              f"{format_money(amount)} from #{src} to #{dst}")
            return
        self.wrote("transactions", out.txn_id,
                   f"{owner.name} sent {format_money(amount)} #{src} -> #{dst}"
                   f"  (two entries, one transaction)")

    def admin_action(self):
        account_id, _ = self.rng.choice(self.accounts)
        reason = self.rng.choice(REASONS)
        if self.rng.random() < 0.5:
            account = self.store.get_account(account_id)
            freeze = account.status == "ACTIVE"
            self.svc.set_frozen(account_id, freeze, reason, self.admin)
            self.wrote("audit_log", len(self.svc.audit),
                       f"admin {'froze' if freeze else 'unfroze'} #{account_id}: {reason}")
            self.wrote("accounts", account_id,
                       f"status is now {'FROZEN' if freeze else 'ACTIVE'}")
        else:
            amount = self.rng.randrange(500, 20_000, 100)
            direction = self.rng.choice(["CREDIT", "DEBIT"])
            try:
                txn = self.svc.adjust(account_id, amount, direction, reason, self.admin)
            except BankError as exc:
                self.refused(exc, f"admin tried to {direction} {format_money(amount)}")
                return
            self.wrote("transactions", txn.txn_id,
                       f"admin {direction} {format_money(amount)} on #{account_id}")
            self.wrote("audit_log", len(self.svc.audit), f"reason recorded: {reason}")

    # ---- the loop ----

    def step(self, password_hash):
        """One action, chosen to look like ordinary traffic."""
        roll = self.rng.random()
        if roll < 0.10:
            self.new_customer(password_hash)
        elif roll < 0.45:
            self.deposit()
        elif roll < 0.75:
            self.withdraw()
        elif roll < 0.92:
            self.transfer()
        else:
            self.admin_action()


def build_parser():
    p = argparse.ArgumentParser(
        description="Generate live banking activity against MongoDB Atlas")
    p.add_argument("--db", default=None,
                   help="database to write to (default: MONGODB_DB + '_sim')")
    p.add_argument("--reset", action="store_true",
                   help="empty the database before starting")
    p.add_argument("--steps", type=int, default=0,
                   help="stop after this many actions (default: until Ctrl+C)")
    p.add_argument("--delay", type=float, default=2.0,
                   help="seconds between actions (default: 2)")
    p.add_argument("--fast", action="store_true",
                   help="no delay, for filling a database quickly")
    p.add_argument("--seed", type=int, default=None,
                   help="fix the random seed, to get the same run twice")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    from bank import config
    config.load_env()
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        print("  This writes to MongoDB, so it needs MONGODB_URI in .env.")
        print("  See mongo.md, or run:  python tools/check_mongo.py")
        return 1
    try:
        from bank.mongo_store import MongoStore
    except ImportError:
        print("  Needs pymongo:  python -m pip install -r requirements.txt")
        return 1

    # Its own database by default, so a simulation left running does not bury
    # the seeded demo data under a few hundred invented transactions.
    db_name = args.db or (os.environ.get("MONGODB_DB", "simple_bank") + "_sim")
    delay = 0.0 if args.fast else max(0.0, args.delay)

    print("=" * 70)
    print("  Simple Bank: live traffic against MongoDB Atlas")
    print("=" * 70)
    print(f"  database: {db_name}")
    print(f"  pace:     {'as fast as possible' if not delay else f'{delay:g}s between actions'}")
    print()
    print("  Watch it arrive:  cloud.mongodb.com -> Cluster0 -> Browse Collections")
    print(f"                    -> {db_name} -> users / accounts / transactions")
    print("  Atlas does NOT refresh by itself. Press its refresh icon.")
    print()
    print("  Ctrl+C to stop.")
    print("-" * 70)

    store = MongoStore(uri, db_name)
    if args.reset:
        store.reset()
        print(f"  {now()}  emptied {db_name}")
    svc = BankService(store)
    rng = random.Random(args.seed)
    sim = Sim(svc, store, rng)

    # One hash, reused. See ensure_cast().
    from bank import hash_password
    print(f"  {now()}  deriving one password hash to share (about a second)...")
    password_hash = hash_password("SimDemo123!")

    try:
        sim.ensure_cast(password_hash)
        n = 0
        while args.steps == 0 or n < args.steps:
            if delay:
                time.sleep(delay)
            sim.step(password_hash)
            n += 1
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        print("-" * 70)
        counts = {
            "users": len(store.all_users()),
            "accounts": len(store.all_accounts()),
        }
        print(f"  wrote {sim.stats['written']} document(s), "
              f"{sim.stats['refused']} action(s) refused by a rule")
        print(f"  {db_name} now holds {counts['users']} users "
              f"and {counts['accounts']} accounts")

        # The invariant, checked against everything the simulation just did.
        broken = svc.reconcile_all()
        if broken:
            print(f"  RECONCILIATION FAILED for {len(broken)} account(s): {broken}")
        else:
            print(f"  all {counts['accounts']} accounts reconcile: "
                  f"balance == sum(ledger)")
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
