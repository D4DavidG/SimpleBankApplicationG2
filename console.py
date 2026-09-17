"""Interactive console. Type the values in, one prompt at a time.

    python console.py             # in memory, nothing is saved
    python console.py --mongo     # writes to MongoDB Atlas, and stays there

Built for demonstrating live. `demo.py` is the scripted version, which runs the
same rules start to finish without anybody typing; this is the one for when the
room wants to pick the name, or the amount, or the thing that gets rejected.

WHAT IT IS NOT
--------------
Not a second implementation of anything. Every option below calls exactly the
method `api.py` calls for the matching HTTP route, so what happens here is what
happens over REST - there is no separate code path that could be right while the
API is wrong.

MONEY IS TYPED IN DOLLARS AND STORED IN CENTS
---------------------------------------------
Type `25.50`; it is converted once, here, and everything below this line is an
integer number of cents. That conversion is deliberately visible in the output
(`25.50  ->  2550 cents`), because it is the single design decision most worth
explaining while somebody is watching.

Nothing here can raise out of the menu. Every rule the backend enforces arrives
as a printed refusal and returns you to the prompt, which is the entire point:
during a demo the rejections are the interesting part, and a traceback would end
the demo.
"""
import argparse
import os
import sys

from bank import (
    BankError, BankService, BankStore, format_money,
)

DEMO_DB_SUFFIX = "_console"


# ----------------------------------------------------------------- prompting

class Quit(Exception):
    """Raised by the prompts when the user asks to leave."""


def ask(label, *, required=True, default=None):
    """One prompt. Blank keeps the default; `q` leaves."""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            value = input(f"  {label}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise Quit from None
        if value.lower() in ("q", "quit", "exit"):
            raise Quit
        if not value and default is not None:
            return default
        if value or not required:
            return value
        print("      (required)")


def ask_int(label, *, default=None):
    while True:
        raw = ask(label, default=default)
        try:
            return int(str(raw).strip())
        except ValueError:
            print("      that is not a whole number")


def ask_money(label):
    """Dollars in, cents out, with the conversion shown.

    Accepts `25.50`, `25`, `1,234.56` or `$25.50`, because people type all four.
    Rejects three decimal places rather than rounding them: a third digit means
    the person meant something this system cannot represent, and quietly
    dropping it is how a bank loses a cent.
    """
    while True:
        raw = ask(label).replace("$", "").replace(",", "").strip()
        try:
            if "." in raw:
                whole, _, frac = raw.partition(".")
                if len(frac) > 2:
                    print("      at most two decimal places")
                    continue
                cents = int(whole or "0") * 100 + int(frac.ljust(2, "0"))
            else:
                cents = int(raw) * 100
        except ValueError:
            print("      that is not an amount, e.g. 25.50")
            continue
        print(f"      {raw}  ->  {cents} cents   (stored as an integer)")
        return cents


def ask_choice(label, options):
    """A numbered choice. `options` is a list of (key, label) pairs."""
    for i, (_, text) in enumerate(options, 1):
        print(f"      {i}. {text}")
    while True:
        raw = ask(label)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print(f"      choose 1 to {len(options)}")


def say(msg):
    print(f"  OK    {msg}")


def refused(exc):
    """A rule stopped it. This is a result, not a crash."""
    print(f"  NO    {type(exc).__name__}: {exc}")


GLOSSARY = [
    ("THE FIVE COLLECTIONS IN ATLAS", [
        ("users",
         "One document per person. Name, email, role, and the password as a "
         "PBKDF2 hash - open one and look: there is no plaintext password "
         "anywhere in the document, and the hash cannot be reversed."),
        ("accounts",
         "One document per account. Who owns it (user_id), what type, its "
         "status, and balance as a whole number of cents."),
        ("transactions",
         "The ledger. One document per movement of money, and they are never "
         "edited or deleted. A mistake is corrected by posting another entry, "
         "which is how real accounting works."),
        ("counters",
         "Five documents, one per collection, each holding the last id handed "
         "out. Asking for the next id and increasing it happen in a single "
         "database operation, so two people registering at the same instant "
         "cannot be given the same number. This is what AUTO_INCREMENT does in "
         "SQL; MongoDB has no such thing, so the pattern is built here."),
        ("audit_log",
         "Every admin action: who did it, to what, when, and the reason they "
         "typed. Separate from the ledger because it answers a different "
         "question - not 'where did the money go' but 'who touched this'."),
    ]),
    ("WORDS ON SCREEN", [
        ("_id",
         "MongoDB's primary key. Every document has one, it is unique inside "
         "its collection, and it is indexed automatically. Ours is the plain "
         "integer from counters, not MongoDB's default random ObjectId, "
         "because '#7' reads better in a demo than '507f1f77bcf86cd799439011'."),
        ("account number",
         "The _id of the document in accounts. It is printed in a box when the "
         "account is opened, listed again at every prompt that needs it, and "
         "offered as the default - press ENTER to take it."),
        ("reference id / client_txn_id",
         "A label the CALLER invents for one transaction. The bank stores it "
         "and refuses any later transaction carrying the same label. That is "
         "what stops a double-clicked Pay button charging twice. It is not "
         "something to look up, and it is not the account number."),
        ("balance in cents",
         "$25.50 is stored as the integer 2550. Never a float: 0.1 + 0.2 is "
         "0.30000000000000004 in binary floating point, and a bank that "
         "rounds like that loses money. The dollars-to-cents conversion is "
         "printed at every prompt so it can be seen happening."),
        ("the ledger",
         "The transactions collection read as a whole. balance is not the "
         "source of truth - the sum of the entries is. Option 7 adds them up "
         "inside the database and checks the two agree."),
        ("DEPOSIT / WITHDRAWAL / TRANSFER_IN / TRANSFER_OUT / ADJUSTMENT",
         "The txn_type field. A transfer writes TWO entries, one of each "
         "direction, in a single MongoDB transaction - both land or neither "
         "does, so no one can ever observe the money in flight."),
        ("status: ACTIVE / FROZEN / CLOSED",
         "On the account document. A frozen account refuses deposits as well "
         "as withdrawals, which surprises people and is correct: a freeze is "
         "usually a fraud hold, and taking more money in is not safer."),
        ("audit reason",
         "Ten characters minimum, enforced by the service. 'ok' is not a "
         "reason, and an audit trail full of 'ok' is not an audit trail."),
    ]),
    ("REFUSALS, AND WHY EACH ONE IS GOOD NEWS", [
        ("AccountNotFound on someone else's account",
         "Not 'not allowed'. Saying 'you may not see this' would confirm the "
         "account exists, which leaks. The same answer comes back whether the "
         "account belongs to another person or does not exist at all."),
        ("DuplicateTransaction",
         "That reference id has already been used. The second attempt wrote "
         "nothing - it did not half-succeed."),
        ("InsufficientFunds",
         "Checked and written inside one atomic block, so a second request "
         "cannot slip between the check and the write and spend it twice."),
        ("AccountNotActive",
         "The account is frozen or closed."),
        ("StorageUnavailable",
         "The database could not be reached. It becomes HTTP 503, not a "
         "stack trace - api.py does not import pymongo at all, so a driver "
         "problem cannot leak out of the HTTP layer as a 500."),
    ]),
]


# -------------------------------------------------------------------- actions

class Console:
    def __init__(self, svc, storage, mongo):
        self.svc = svc
        self.storage = storage
        self.mongo = mongo
        self.actor = None          # who is signed in
        self.db_name = getattr(svc.store, "db_name", None)
        # Demo aids. The account number and the reference id are the two things
        # a person forgets between one menu option and the next, so the console
        # remembers them and offers them back instead of expecting a good guess.
        self.last_account = None
        self.ref_seq = 0
        self.used_refs = []

    # ---- helpers ----

    def look(self, *rows):
        """Point at the documents the last action wrote, so they can be found.

        The whole reason this console exists is to be run beside the Atlas Data
        Explorer in a browser. A line saying "created user #15" is not enough to
        go and find it with: you need the database, the collection and the `_id`,
        which is what this prints.

        Atlas does not refresh by itself. That is worth repeating on screen,
        because the first reaction to an empty-looking collection is to assume
        the write failed rather than that the page is stale.
        """
        if not self.mongo:
            print("      (in memory: there is nothing to look at. "
                  "Restart with --mongo.)")
            return
        print()
        print(f"  >>  IN ATLAS   database   {self.db_name}")
        for collection, doc_id, note in rows:
            where = f"_id {doc_id}" if doc_id is not None else ""
            print(f"      {'':10} collection {collection:<14} {where:<10} {note}")
        print(f"      {'':10} press the REFRESH icon in Browse Collections")

    def wrote_nothing(self, why):
        """Some options deliberately write nothing. Say so rather than leaving a
        silence that looks like a failure."""
        print()
        print(f"  >>  IN ATLAS   nothing changed - {why}")

    def need_actor(self):
        if self.actor is None:
            print("  NO    nobody is signed in. Use 1 to register or 2 to log in.")
            return False
        return True

    def show_accounts(self):
        accounts = self.svc.my_accounts(self.actor)
        if not accounts:
            print("      (no accounts yet - use 3 to open one)")
        for a in accounts:
            print(f"      #{a.account_id:<4} {a.account_type:<9} "
                  f"{format_money(a.balance):>13}  {a.status}")
        return accounts

    def ask_account(self, label="Account number"):
        """Ask for an account number, having first shown which ones exist.

        Nobody should have to remember a number this program already knows, so
        the accounts are listed and the most recently used one is the default:
        press ENTER and it is filled in. Any other number is still accepted,
        including one belonging to somebody else - that refusal is worth showing.
        """
        accounts = self.show_accounts()
        mine = [a.account_id for a in accounts]
        if mine and self.last_account not in mine:
            self.last_account = mine[0]
        if mine:
            print("      ENTER takes the default below; any other number is")
            print("      accepted too, including one that is not yours")
        return ask_int(label, default=self.last_account)

    def ask_ref(self):
        """Ask for the idempotency key, explaining it where it is being typed.

        This is the prompt that confuses people, because it reads as though it
        wants something looked up. It does not: the value is invented by the
        caller. A real client sends a UUID it generated before the request; a
        readable counter is used here so the duplicate refusal can be triggered
        on cue in front of a room.
        """
        print()
        print("      Reference id = a label YOU invent for this one transaction.")
        print("      The bank stores it and refuses any later transaction that")
        print("      carries the same one. That is what stops a double-clicked")
        print("      Pay button charging twice. It is not something to look up.")
        if self.used_refs:
            print(f"      used so far: {', '.join(self.used_refs)}")
            print("      ^ type one of those back in to watch it be refused")
        self.ref_seq += 1
        suggested = f"ref-{self.ref_seq:03d}"
        print("      ENTER takes the suggestion; type 'none' to send no reference")
        ref = str(ask("Reference id", default=suggested)).strip()
        if ref.lower() in ("none", "no", "-"):
            return None
        return ref

    # ---- 1 ----

    def register(self):
        print("\n  Register a user")
        name = ask("Name")
        email = ask("Email")
        password = ask("Password (not hidden)")
        role = ask_choice("User or Admin", [("CUSTOMER", "User"), ("ADMIN", "Admin")])
        user = self.svc.register_user(name, email, role=role, password=password)
        self.actor = user
        say(f"created user #{user.user_id}: {user.name} <{user.email}> ({user.role})")
        say("signed in as them")
        self.look(
            ("users", user.user_id, "the new person"),
            ("counters", "'users'", "seq went up by one - this is AUTO_INCREMENT"),
        )
        say("note: the password is stored only as a PBKDF2 hash. Open the")
        say("      document and check - there is no plaintext anywhere in it.")

    # ---- 2 ----

    def login(self):
        print("\n  Log in")
        email = ask("Email")
        password = ask("Password (not hidden)")
        # The real authenticate(), so a wrong password is refused here exactly as
        # it would be at POST /api/auth/login.
        self.actor = self.svc.authenticate(email, password)
        say(f"signed in as {self.actor.name} ({self.actor.role})")
        self.wrote_nothing("logging in is a read. It checks the stored hash "
                           "and writes no document")

    # ---- 3 ----

    def open_account(self):
        if not self.need_actor():
            return
        print(f"\n  Open an account for {self.actor.name}")
        kind = ask_choice("Account type",
                          [("CHECKING", "Checking"), ("SAVINGS", "Savings")])
        opening = ask_money("Opening balance (0 for empty)")
        account = self.svc.open_account(self.actor, kind, opening)
        self.last_account = account.account_id
        say(f"opened account #{account.account_id}, "
            f"balance {format_money(account.balance)}")
        # The account number is the one thing that has to survive until the next
        # menu option, so it gets more of the screen than a line of prose.
        box = [f"ACCOUNT NUMBER {account.account_id}",
               "options 4, 5, 6 and 7 ask for this number"]
        width = max(len(line) for line in box) + 4
        print()
        print("      +" + "-" * width + "+")
        for line in box:
            print("      |  " + line.ljust(width - 4) + "  |")
        print("      +" + "-" * width + "+")
        rows = [("accounts", account.account_id,
                 f"balance is stored as {account.balance}, an integer")]
        if opening:
            say("the opening balance was NOT written straight into the balance")
            say("field. It was posted to the ledger as a DEPOSIT, like any other")
            say("credit, so that balance still equals the sum of the entries.")
            say("Every cent here can be traced to an entry that put it there,")
            say("which is what option 7 re-checks.")
            entries = self.svc.store.transactions_for_account(account.account_id)
            if entries:
                rows.append(("transactions", entries[0].txn_id,
                             "the opening DEPOSIT - the balance did not appear "
                             "from nowhere"))
        self.look(*rows)

    # ---- 4 and 5 ----

    def move_money(self, kind):
        if not self.need_actor():
            return
        print(f"\n  {kind.title()}")
        # Deliberately not "you have no accounts, go away". Typing someone
        # else's number here is the point: ownership is checked by the service,
        # and the refusal is one of the better things to show.
        account_id = self.ask_account()
        amount = ask_money("Amount")
        ref = self.ask_ref()
        fn = self.svc.deposit if kind == "deposit" else self.svc.withdraw
        txn = fn(account_id, amount, self.actor, client_txn_id=ref)
        self.last_account = account_id
        if ref and ref not in self.used_refs:
            self.used_refs.append(ref)
        account = self.svc.get_account_for(account_id, self.actor)
        say(f"txn #{txn.txn_id} {txn.txn_type} {format_money(txn.amount)}")
        say(f"account #{account_id} is now {format_money(account.balance)}")
        if ref:
            say(f"reference {ref!r} is now used - sending it again will be refused")
        self.look(
            ("transactions", txn.txn_id, f"a new {txn.txn_type} entry"),
            ("accounts", account_id,
             f"balance field changed to {account.balance}"),
        )

    # ---- 6 ----

    def transfer(self):
        if not self.need_actor():
            return
        print("\n  Transfer")
        if not self.show_accounts():
            return
        src = ask_int("From account", default=self.last_account)
        dst = ask_int("To account (may belong to someone else)")
        amount = ask_money("Amount")
        out, inn = self.svc.transfer(src, dst, amount, self.actor)
        self.last_account = src
        say(f"sent {format_money(out.amount)} from #{src} to #{dst}")
        say("both legs and both ledger entries happened together, or neither would")
        self.look(
            ("transactions", out.txn_id, "TRANSFER_OUT"),
            ("transactions", inn.txn_id, "TRANSFER_IN - same MongoDB transaction"),
            ("accounts", src, "debited"),
            ("accounts", dst, "credited"),
        )
        say("four documents, one transaction. Atlas never shows a state where the")
        say("money has left one account and not arrived at the other.")
        self.show_accounts()

    # ---- 7 ----

    def history(self):
        if not self.need_actor():
            return
        print("\n  Transaction history")
        print("      (any account number is accepted here, including one that is")
        print("       not yours - what comes back is the interesting part)")
        account_id = self.ask_account()
        rows, total = self.svc.history(account_id, self.actor, page_size=20)
        print(f"\n      {total} entries, newest first:")
        for txn in rows:
            print(f"      {txn}")
        stored, ledger = self.svc.reconcile(account_id)
        mark = "OK" if stored == ledger else "MISMATCH"
        print(f"\n      balance {format_money(stored)} == "
              f"ledger {format_money(ledger)}   [{mark}]")
        self.wrote_nothing("reading history changes nothing. The ledger sum was "
                           "computed by the database, not by this program")

    # ---- 8 ----

    def admin(self):
        if not self.need_actor():
            return
        print("\n  Admin")
        what = ask_choice("Do what", [
            ("freeze", "Freeze or unfreeze an account"),
            ("adjust", "Post a correcting adjustment"),
            ("audit", "Show the audit log"),
            ("reconcile", "Reconcile every account"),
            ("users", "List every user"),
        ])
        if what == "freeze":
            account_id = ask_int("Account number", default=self.last_account)
            on = ask_choice("Action", [(True, "Freeze"), (False, "Unfreeze")])
            reason = ask("Reason (10 characters or more)")
            account = self.svc.set_frozen(account_id, on, reason, self.actor)
            say(f"account #{account_id} is now {account.status}")
            self.look(
                ("accounts", account_id, f"status field is now {account.status}"),
                ("audit_log", len(self.svc.audit), "who did it, and the reason given"),
            )
        elif what == "adjust":
            account_id = ask_int("Account number", default=self.last_account)
            direction = ask_choice("Direction",
                                   [("CREDIT", "Credit (add)"), ("DEBIT", "Debit (remove)")])
            amount = ask_money("Amount")
            reason = ask("Reason (10 characters or more)")
            txn = self.svc.adjust(account_id, amount, direction, reason, self.actor)
            say(f"posted txn #{txn.txn_id}: {direction} {format_money(txn.amount)}")
            say("an adjustment is a ledger entry. There is no set_balance anywhere")
            self.look(
                ("transactions", txn.txn_id,
                 "carries adjusted_by and reason - a plain deposit has neither"),
                ("accounts", account_id, "balance moved, with that entry to explain it"),
                ("audit_log", len(self.svc.audit), "the admin action, recorded separately"),
            )
        elif what == "audit":
            entries = self.svc.audit_log(self.actor)
            print(f"\n      {len(entries)} admin action(s):")
            for e in entries:
                print(f"      {e}")
        elif what == "reconcile":
            broken = self.svc.reconciliation_report(self.actor)
            if broken:
                print(f"      RECONCILIATION FAILED: {broken}")
            else:
                n = len(self.svc.all_accounts(self.actor))
                say(f"all {n} accounts reconcile: balance == sum(ledger)")
        elif what == "users":
            for u in self.svc.all_users(self.actor):
                print(f"      #{u.user_id:<4} {u.role:<9} {u}")

    # ---- 9 ----

    def prove_stored(self):
        """Read the records back through a connection that has never seen them."""
        if not self.mongo:
            print("  NO    in-memory mode: there is nothing to read back.")
            print("        Restart with --mongo to show this.")
            return
        print("\n  Reading back from Atlas through a second connection")
        from bank.mongo_store import MongoStore
        other = MongoStore(os.environ["MONGODB_URI"], self.svc.store.db_name)
        try:
            users = other.all_users()
            accounts = other.all_accounts()
            plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"  # noqa: E731
            say(f"{plural(len(users), 'user')} and "
                f"{plural(len(accounts), 'account')} in the database")
            for a in accounts[-5:]:
                print(f"      #{a.account_id:<4} {a.account_type:<9} "
                      f"{format_money(a.balance):>13}  {a.status}")
            print("\n      none of that came from this program's objects. It was")
            print("      read out of Atlas by a connection that never saw them.")
        finally:
            other.close()


    # ---- ? ----

    def glossary(self):
        """Every term this console puts on screen, with the reason behind it.

        Here rather than only in the README because the moment the question gets
        asked is the moment somebody is looking at the terminal.
        """
        for heading, rows in GLOSSARY:
            print()
            print(f"  {heading}")
            print(f"  {'-' * len(heading)}")
            for term, text in rows:
                print(f"\n  {term}")
                # Wrapped here rather than stored pre-wrapped, so the text above
                # stays editable as prose.
                line = "    "
                for word in text.split():
                    if len(line) + len(word) + 1 > 76:
                        print(line)
                        line = "    "
                    line += word + " "
                print(line.rstrip())
        print()


MENU = """
  1  Register a user            5  Withdraw
  2  Log in as someone else     6  Transfer
  3  Open an account            7  Account history
  4  Deposit                    8  Admin actions
                                9  Prove it is in the database
  ?  What every word here means
  0  Quit
"""


def build_parser():
    p = argparse.ArgumentParser(description="Interactive console for the bank backend")
    p.add_argument("--mongo", action="store_true",
                   help="write to MongoDB Atlas instead of memory")
    p.add_argument("--db", default=None,
                   help="with --mongo: database name (default: MONGODB_DB + '_console')")
    p.add_argument("--reset", action="store_true",
                   help="with --mongo: empty the database first")
    return p


def open_store(args):
    if not args.mongo:
        return BankStore(), "in memory (nothing is saved when you quit)", False

    from bank import config
    config.load_env()
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        print("  --mongo needs MONGODB_URI in .env. See mongo.md, or run:")
        print("      python tools/check_mongo.py")
        raise SystemExit(1)
    try:
        from bank.mongo_store import MongoStore
    except ImportError:
        print("  --mongo needs pymongo:  python -m pip install -r requirements.txt")
        raise SystemExit(1)

    # Its own database by default. Typing made-up names into the shared demo data
    # is how the shared demo data stops being demonstrable.
    db_name = args.db or (os.environ.get("MONGODB_DB", "simple_bank") + DEMO_DB_SUFFIX)
    store = MongoStore(uri, db_name)
    if args.reset:
        store.reset()
    return store, f"MongoDB Atlas, database {db_name!r} (saved)", True


def main(argv=None):
    args = build_parser().parse_args(argv)
    store, storage, mongo = open_store(args)
    svc = BankService(store)
    console = Console(svc, storage, mongo)

    print("=" * 62)
    print("  Simple Bank: interactive console")
    print("=" * 62)
    print(f"  storage: {storage}")
    print("  amounts are typed in dollars and stored as integer cents")
    print("  'q' at any prompt goes back to the menu")
    if mongo:
        print()
        print("  WATCH IT LIVE, in a browser beside this terminal:")
        print("    cloud.mongodb.com -> Cluster0 -> Browse Collections")
        print(f"    -> database: {store.db_name}")
        print("  After each action this prints the collection and _id to open.")
        print("  Atlas does NOT refresh by itself - press its refresh icon.")

    actions = {
        "1": console.register,
        "2": console.login,
        "3": console.open_account,
        "4": lambda: console.move_money("deposit"),
        "5": lambda: console.move_money("withdraw"),
        "6": console.transfer,
        "7": console.history,
        "8": console.admin,
        "9": console.prove_stored,
        "?": console.glossary,
    }

    while True:
        who = f"{console.actor.name} ({console.actor.role})" if console.actor else "nobody"
        print(MENU)
        print(f"  signed in: {who}")
        try:
            choice = input("\n  Choose: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "0"

        if choice == "0":
            break
        action = actions.get(choice)
        if action is None:
            print("  NO    pick a number from the menu")
            continue
        try:
            action()
        except Quit:
            print("      (back to the menu)")
        except BankError as exc:
            # Every rule in services.py arrives here. A refusal is a result.
            refused(exc)
        except (ValueError, TypeError) as exc:
            refused(exc)
        except Exception as exc:                      # noqa: BLE001
            # Anything unexpected still must not end the session mid-demo.
            print(f"  NO    unexpected {type(exc).__name__}: {exc}")

    if hasattr(store, "close"):
        store.close()
    print("\n  bye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
