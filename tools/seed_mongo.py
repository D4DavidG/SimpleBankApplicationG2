"""Load the demo roster into MongoDB Atlas.

    python tools/seed_mongo.py              # seed, refusing to touch a non-empty db
    python tools/seed_mongo.py --reset      # wipe first, then seed
    python tools/seed_mongo.py --db simple_bank      # override MONGODB_DB

THIS REPLACES SECTION 5 OF `seed_data_bank_app.md`
--------------------------------------------------
That document contains a `mongosh` script of `insertMany` calls using
`NumberDecimal("2480.00")`. **Do not run it.** It was written before this codebase
moved to integer cents, and it writes `Decimal128` where the code requires `int`:

    >>> to_cents(Decimal128("2480.00"))
    TypeError: Money must be an int number of cents, e.g. 2500 for 25.00

The failure is loud rather than silent - `money.py` refuses anything that is not
an `int` precisely so that a units mismatch cannot become a quiet 100x error -
but it means a database seeded that way is one the application cannot read at
all, while looking perfectly correct in the Atlas data explorer.

WHY THIS IS A SCRIPT AND NOT A PASTED BLOB
------------------------------------------
Hardcoded balances and their ledger rows can disagree. This script has nothing to
disagree with: it calls `seed.load()`, which opens every account at zero and
replays each transaction through `BankService.deposit` and `.withdraw` - the same
methods an HTTP request reaches. Reconciliation is therefore true by construction
rather than asserted afterwards, and seeding doubles as a test of the rules.

It also means there is exactly one seed roster in the project. The in-memory
server and the Mongo server load the same fourteen users and seventy-three
transactions from the same file, so a bug reproduced on one is reproducible on
the other.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bank import BankService                      # noqa: E402
from bank import seed as seed_module              # noqa: E402
from bank import config                           # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seed MongoDB with the demo roster")
    p.add_argument("--reset", action="store_true",
                   help="drop the collections first (destructive)")
    p.add_argument("--db", default=None,
                   help="database name, overriding MONGODB_DB")
    p.add_argument("--yes", action="store_true",
                   help="skip the confirmation prompt for --reset")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config.load_env()

    try:
        from bank.mongo_store import MongoStore
    except ImportError:
        print("pymongo is not installed.  pip install -r requirements.txt")
        return 1

    db_name = args.db or config.mongo_db_name()
    print("=" * 70)
    print("  Seeding MongoDB")
    print("=" * 70)
    print(f"  database: {db_name}")

    try:
        store = MongoStore(db_name=db_name)
    except Exception as exc:
        print(f"\n  Could not connect: {exc}")
        print("  Run `python tools/check_mongo.py` to find out why.")
        return 1

    existing = store.stats()
    print(f"  currently holds: {existing['users']} users, "
          f"{existing['accounts']} accounts, {existing['transactions']} transactions")

    if any(existing.values()):
        if not args.reset:
            print("\n  This database already has data. Refusing to seed on top of it,")
            print("  because the roster would collide on its email addresses and you")
            print("  would get a half-loaded database.")
            print("\n  Re-run with --reset to wipe it first.")
            return 1
        # Deleting someone's data is worth one deliberate keystroke, and the
        # shared database is the one people demo from.
        if not args.yes:
            print(f"\n  --reset will PERMANENTLY DELETE everything in {db_name!r}.")
            reply = input("  Type the database name to confirm: ").strip()
            if reply != db_name:
                print("  Names did not match. Nothing was deleted.")
                return 1
        print("  dropping collections...")
        store.drop_everything()
        store.ensure_indexes()

    print()
    service = BankService(store)
    summary = seed_module.load(service)

    print(f"  seeded {summary['users']} users, {summary['accounts']} accounts, "
          f"{summary['transactions']} transactions")
    print("  every account reconciles: balance == sum(ledger)")
    print()
    print(f"  demo password: {summary['password']}")
    print(f"  admin logins:  {', '.join(summary['admins'])}")
    print()
    print("  Start the API against it with:  python server.py --mongo")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
