"""Start the REST API. Run with: python server.py

    python server.py                  # port 8000, seeded with the cohort roster
    python server.py --port 9000      # somewhere else
    python server.py --empty          # no seed data, register your own users
    python server.py --mongo          # persist to MongoDB Atlas instead of memory

By default everything is in memory, so stopping the server discards every account
and every transaction. That is a feature for a demo - each run starts from the
same known state - and it is why it stays the default.

`--mongo` swaps `BankStore` for `MongoStore` and changes nothing else. That one
substitution is the entire database phase from this file's point of view, which
is what the repository layer was for. It needs `.env` filled in; see mongo.md,
and run `python tools/check_mongo.py` first if anything is unclear.
"""
import argparse
import os
import sys

from bank import BankService, BankStore, serve
from bank import config
from bank import seed as seed_module
from bank.security import new_secret


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple Bank Application API")
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to bind (default: 127.0.0.1, localhost only)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    parser.add_argument("--empty", action="store_true",
                        help="start with no data instead of loading the demo roster")
    parser.add_argument("--mongo", action="store_true",
                        help="persist to MongoDB Atlas instead of memory (see mongo.md)")
    parser.add_argument("--db", default=None,
                        help="with --mongo: database name, overriding MONGODB_DB")
    return parser


def build_store(args):
    """Choose the repository. The only place in the program that decides this.

    Importing MongoStore inside the branch, rather than at the top of the file,
    is what keeps `python server.py` working on a machine with nothing installed.
    pymongo is required only by the people who ask for it.
    """
    if not args.mongo:
        return BankStore(), "in memory (nothing is saved when this process exits)"

    # Check for pymongo itself, not for the mongo_store import. That module
    # imports pymongo inside MongoStore.__init__ - which is what keeps pymongo
    # optional - so importing it succeeds here even when the driver is absent,
    # and the failure would otherwise arrive below wearing a "could not connect"
    # message when the real answer is "you have not installed it".
    try:
        import pymongo  # noqa: F401
    except ImportError:
        print("  --mongo needs the MongoDB driver, which is not installed here.")
        print("      pip install -r requirements.txt")
        print(f"  (installing into the Python you are running: {sys.prefix})")
        raise SystemExit(1)

    from bank.mongo_store import MongoStore

    db_name = args.db or config.mongo_db_name()
    try:
        store = MongoStore(db_name=db_name)
    except Exception as exc:
        print(f"  Could not connect to MongoDB: {exc}")
        print("  Run `python tools/check_mongo.py` to find out why.")
        raise SystemExit(1)
    return store, f"MongoDB, database {db_name!r}"


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    config.load_env()

    # Compose the layers. This is the only place the whole stack is assembled,
    # and it reads as the architecture diagram: store -> service -> api.
    store, storage_description = build_store(args)
    service = BankService(store)

    print("=" * 70)
    print("  Simple Bank Application: backend")
    print("=" * 70)
    print(f"  storage: {storage_description}")

    # Whether to load the roster into this store now. In memory that is every
    # start, because memory is empty every start. Mongo keeps what the last run
    # left, so seeding there is a setup step (tools/seed_mongo.py) and not
    # something a restart should redo - re-running the roster against a populated
    # database would collide on its email addresses half way through.
    load_seed = not args.empty and not args.mongo

    if args.mongo:
        existing = store.stats()
        if any(existing.values()):
            print(f"  holding {existing['users']} users, {existing['accounts']} accounts, "
                  f"{existing['transactions']} transactions")
            print(f"  every seeded user's password is: {seed_module.DEMO_PASSWORD}")
        else:
            print("  the database is EMPTY. Load the demo roster with:")
            print("      python tools/seed_mongo.py")
            print("  or register a user through POST /api/auth/register.")
    elif args.empty:
        print("  starting empty (--empty). POST /api/auth/register to create a user.")

    if load_seed:
        # Loading the seed replays ~73 transactions through the real service
        # methods and asserts the result reconciles, so a failure here is a
        # genuine bug report and not a data problem.
        summary = seed_module.load(service)
        print(f"  seeded {summary['users']} users, {summary['accounts']} accounts, "
              f"{summary['transactions']} transactions")
        print("  all accounts reconcile: balance == sum(ledger)")
        print()
        print(f"  every seeded user's password is: {summary['password']}")
        print("  customer login: aaron.forrester@example.com")
        # Two admins, so admin-to-admin visibility and the audit trail can both
        # be demonstrated. Either works; the Postman collection uses David.
        print(f"  admin logins:   {', '.join(summary['admins'])}")

    print()
    # A random per-process secret is the safe default - no secret is ever
    # committed - and the only consequence is that tokens do not survive a
    # restart. Say which one is in use, so a 401 after a restart is not a mystery.
    secret = new_secret()
    if os.environ.get("BANK_SECRET"):
        print("  signing secret: taken from $BANK_SECRET")
    else:
        print("  signing secret: random for this process "
              "(tokens stop working when you restart)")
    print()

    serve(service, host=args.host, port=args.port, secret=secret)
    return 0


if __name__ == "__main__":
    sys.exit(main())
