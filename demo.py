"""Console walkthrough of the whole backend. Run with: python demo.py

Sections 1 to 10 exercise every rule in `services.py` by calling methods, and
print what happened. Section 11 then reaches the same rules through the REST
layer, so the same behaviour is visible as HTTP status codes.

No input required and no server needed, so it is safe to run during a demo
without typing under pressure or hoping a port is free.
"""
import json
from decimal import Decimal

from bank import (
    AccountNotActive, AccountNotFound, BankAPI, BankError, BankService, BankStore,
    DuplicateTransaction, InsufficientFunds, InvalidAmount, NotAuthorized,
    format_money, issue_token,
)


def rule(label):
    print(f"\n{'=' * 68}\n{label}\n{'=' * 68}")


def ok(msg):
    print(f"  [ok]       {msg}")


def blocked(exc):
    print(f"  [blocked]  {type(exc).__name__}: {exc}")


def attempt(label, fn):
    """Run something expected to fail and report which rule stopped it."""
    print(f"  attempting: {label}")
    try:
        fn()
        print("  [PROBLEM]  that should not have been allowed")
    except BankError as exc:
        blocked(exc)
    except (ValueError, TypeError) as exc:
        blocked(exc)


def main():
    store = BankStore()
    svc = BankService(store)

    rule("1. Users and accounts")
    aaron = svc.register_user("Aaron Forrester", "aaron.forrester@example.com")
    erik = svc.register_user("Erik Mayes", "erik.mayes@example.com")
    david = svc.register_user("David Gusmao", "david.gusmao@example.com", role="ADMIN")
    ok(f"registered {aaron}")
    ok(f"registered {erik}")
    ok(f"registered {david}  (role: {david.role})")

    checking = svc.open_account(aaron, "CHECKING", "12.50")
    savings = svc.open_account(aaron, "SAVINGS", "500.00")
    erik_acct = svc.open_account(erik, "CHECKING", "84210.75")
    for acct in (checking, savings, erik_acct):
        ok(str(acct))

    attempt("register a second user with Aaron's email",
            lambda: svc.register_user("Impostor", "AARON.FORRESTER@example.com"))

    rule("2. Deposits and withdrawals")
    svc.deposit(checking.account_id, "100.00", aaron)
    ok(f"deposited 100.00, balance now {format_money(checking.balance)}")
    svc.withdraw(checking.account_id, "12.50", aaron)
    ok(f"withdrew 12.50, balance now {format_money(checking.balance)}")

    attempt("withdraw 999.00 from a balance of 100.00",
            lambda: svc.withdraw(checking.account_id, "999.00", aaron))
    attempt("deposit a negative amount",
            lambda: svc.deposit(checking.account_id, "-50.00", aaron))
    attempt("deposit 10.555 (three decimal places)",
            lambda: svc.deposit(checking.account_id, "10.555", aaron))
    attempt("deposit a float instead of a string",
            lambda: svc.deposit(checking.account_id, 10.50, aaron))

    rule("3. Savings accounts hold a minimum (polymorphism, not an if-statement)")
    ok(f"savings balance {format_money(savings.balance)}, "
       f"minimum {format_money(savings.minimum_balance)}, "
       f"available {format_money(savings.available_for_withdrawal())}")
    attempt("withdraw 475.01, one cent past the minimum",
            lambda: svc.withdraw(savings.account_id, "475.01", aaron))
    svc.withdraw(savings.account_id, "475.00", aaron)
    ok(f"withdrew 475.00, balance now {format_money(savings.balance)} (at the minimum)")
    print("     note: services.py never checks the account type. It calls")
    print("     account.can_withdraw(), and the subclass supplies the rule.")

    rule("4. Decimal precision")
    # Account 20 from the seed file: one deposit and two withdrawals that come to
    # exactly 72.10 in Decimal and 72.10000000000001 in float.
    precise = svc.open_account(aaron, "CHECKING")
    svc.deposit(precise.account_id, "115.36", aaron)
    for amount in ["39.80", "3.46"]:
        svc.withdraw(precise.account_id, amount, aaron)
    drift = 115.36 - 39.80 - 3.46
    ok("115.36 - 39.80 - 3.46")
    ok(f"  Decimal : {precise.balance}")
    print(f"  [float] : {drift!r}   <- what the same arithmetic gives in float")

    rule("5. Idempotency: the double-clicked submit button")
    before = checking.balance
    svc.deposit(checking.account_id, "25.00", aaron, client_txn_id="submit-0001")
    ok(f"first submit applied, balance {format_money(checking.balance)}")
    attempt("the same submission again (same client_txn_id)",
            lambda: svc.deposit(checking.account_id, "25.00", aaron,
                                client_txn_id="submit-0001"))
    ok(f"balance unchanged at {format_money(checking.balance)} "
       f"(was {format_money(before)} before the first)")

    rule("6. Ownership: a user may not touch another user's account")
    print(f"  Erik's account is #{erik_acct.account_id}, holding "
          f"{format_money(erik_acct.balance)}")
    attempt("Aaron reads Erik's account",
            lambda: svc.get_account_for(erik_acct.account_id, aaron))
    attempt("Aaron withdraws from Erik's account",
            lambda: svc.withdraw(erik_acct.account_id, "1000.00", aaron))
    attempt("Aaron reads an account id that does not exist at all",
            lambda: svc.get_account_for(99999, aaron))
    print("     note: identical error for 'not yours' and 'does not exist'.")
    print("     A different message would confirm the account is real.")

    admin_view = svc.get_account_for(erik_acct.account_id, david)
    ok(f"admin may read it: {admin_view}")

    rule("7. Admin actions require the role, a reason, and a ledger entry")
    attempt("Aaron freezes an account",
            lambda: svc.set_frozen(erik_acct.account_id, True, "because I felt like it", aaron))
    attempt("admin adjusts with a one-word reason",
            lambda: svc.adjust(checking.account_id, "50.00", "CREDIT", "oops", david))

    svc.adjust(checking.account_id, "50.00", "CREDIT",
               "Reversing a fee misposted on 2026-09-10", david)
    ok(f"admin credited 50.00, balance now {format_money(checking.balance)}")
    ok(f"audit trail: {svc.audit[-1]}")
    print("     note: there is no set_balance method anywhere. Adjustments post a")
    print("     ledger entry, so balance == sum(ledger) still holds afterwards.")

    svc.set_frozen(erik_acct.account_id, True, "Suspected card compromise, under review", david)
    ok(f"admin froze account #{erik_acct.account_id}")
    attempt("Erik deposits into his own frozen account",
            lambda: svc.deposit(erik_acct.account_id, "10.00", erik))

    rule("8. Transfer between accounts")
    svc.set_frozen(erik_acct.account_id, False, "Review complete, no fraud found", david)
    svc.transfer(checking.account_id, erik_acct.account_id, "25.00", aaron)
    ok(f"Aaron sent 25.00 to Erik")
    ok(f"  Aaron  {format_money(checking.balance)}")
    ok(f"  Erik   {format_money(erik_acct.balance)}")
    attempt("transfer more than is available",
            lambda: svc.transfer(checking.account_id, erik_acct.account_id, "99999.00", aaron))

    rule("9. Transaction history")
    rows, total = svc.history(checking.account_id, aaron, page=1, page_size=5)
    print(f"  account #{checking.account_id}, {total} entries, showing the most recent 5:")
    for txn in rows:
        print(f"    {txn}")

    rule("10. Reconciliation: balance must equal the sum of the ledger")
    for account in store.all_accounts():
        stored, ledger = svc.reconcile(account.account_id)
        mark = "ok " if stored == ledger else "BAD"
        print(f"  [{mark}] account #{account.account_id:<3} "
              f"balance {format_money(stored):>13}   ledger {format_money(ledger):>13}")

    broken = svc.reconcile_all()
    print()
    if broken:
        print(f"  RECONCILIATION FAILED for {len(broken)} account(s): {broken}")
    else:
        print(f"  All {len(store.all_accounts())} accounts reconcile. "
              f"Every balance change has a matching ledger entry.")

    api_section(svc, aaron, david, checking, erik_acct)


def api_section(svc, aaron, david, checking, erik_acct):
    """The same rules, reached over the REST layer instead of by calling methods.

    Calls `BankAPI.handle` directly rather than starting a server, so this runs
    in-process with no port and nothing to clean up. The point is the right-hand
    column: every rule demonstrated above now arrives as an HTTP status code, and
    that mapping lives in one table (`ERROR_STATUS` in bank/api.py) rather than
    scattered through the handlers.
    """
    rule("11. The same rules over HTTP")

    api = BankAPI(svc, secret="demo-secret-not-used-anywhere-real")

    def call(label, method, path, body=None, actor=None, expect=None):
        headers = {}
        if actor is not None:
            headers["authorization"] = f"Bearer {issue_token(actor.user_id, actor.role, api.secret)}"
        raw = json.dumps(body).encode("utf-8") if body else b""
        status, payload = api.handle(method, path, raw, headers)
        mark = "ok " if expect is None or status == expect else "BAD"
        detail = payload.get("error") or _summarise(payload)
        print(f"  [{mark}] {status}  {method:<5} {path:<42} {label}")
        if detail:
            print(f"          {detail}")

    print("  Aaron is logged in. Every call below carries his token.\n")
    call("his own account", "GET", f"/api/accounts/{checking.account_id}",
         actor=aaron, expect=200)
    call("deposit 10.00", "POST", f"/api/accounts/{checking.account_id}/deposit",
         {"amount": "10.00"}, aaron, expect=201)
    call("amount as a JSON number, not a string", "POST",
         f"/api/accounts/{checking.account_id}/deposit", {"amount": 10.50}, aaron,
         expect=400)
    call("withdraw more than he has", "POST",
         f"/api/accounts/{checking.account_id}/withdraw", {"amount": "999999.00"},
         aaron, expect=409)
    call("ERIK'S account, by guessing the id", "GET",
         f"/api/accounts/{erik_acct.account_id}", actor=aaron, expect=404)
    call("an account that does not exist", "GET", "/api/accounts/99999",
         actor=aaron, expect=404)
    call("an admin-only route", "GET", "/api/admin/users", actor=aaron, expect=403)
    call("no token at all", "GET", "/api/accounts", expect=401)

    print("\n  The same two requests as an admin:\n")
    call("admin reads Erik's account", "GET",
         f"/api/accounts/{erik_acct.account_id}", actor=david, expect=200)
    call("admin lists every user", "GET", "/api/admin/users", actor=david, expect=200)

    print("\n     note the two 404s. 'not yours' and 'does not exist' are")
    print("     indistinguishable from outside, on purpose: a 403 on the first")
    print("     would confirm the account is real.")


def _summarise(payload: dict) -> str:
    """One short line about a successful response, for the demo output."""
    if "account" in payload:
        account = payload["account"]
        return f"balance {account['balance']}, {account['accountType']}, {account['status']}"
    if "users" in payload:
        return f"{len(payload['users'])} users"
    return ""


if __name__ == "__main__":
    main()
