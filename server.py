"""Start the REST API. Run with: python server.py

    python server.py                  # port 8000, seeded with the cohort roster
    python server.py --port 9000      # somewhere else
    python server.py --empty          # no seed data, register your own users

Everything is in memory, so stopping the server discards every account and every
transaction. That is a feature for a demo - each run starts from the same known
state - and it is the first thing that changes when the database phase lands.
"""
import argparse
import os
import sys

from bank import BankService, BankStore, serve
from bank import seed as seed_module
from bank.security import new_secret


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple Bank Application API")
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to bind (default: 127.0.0.1, localhost only)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    parser.add_argument("--empty", action="store_true",
                        help="start with no data instead of loading the demo roster")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Compose the layers. This is the only place the whole stack is assembled,
    # and it reads as the architecture diagram: store -> service -> api.
    store = BankStore()
    service = BankService(store)

    print("=" * 70)
    print("  Simple Bank Application: backend")
    print("=" * 70)

    if args.empty:
        print("  starting empty (--empty). POST /api/auth/register to create a user.")
    else:
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
