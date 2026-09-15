"""Turning domain objects into the dictionaries that become JSON.

This is a thin layer with one strong opinion, and the opinion is the reason the
layer exists at all rather than the controller calling `dataclasses.asdict`.

MONEY IS SERIALIZED AS A STRING
------------------------------
The brief's sample response is:

    {"accountId": 1, "userName": "John Doe", "balance": 1000.00}

`1000.00` there is a bare JSON number, and that is where the precision this
codebase is careful about everywhere else gets thrown away. JSON has one numeric
type, and every JavaScript client turns it into an IEEE 754 double the instant
`JSON.parse` runs. So `money.py` refuses floats, `Decimal` carries exact cents
through the service layer, and then the response boundary hands the browser a
float anyway.

So every monetary field below goes out as a quoted string:

    {"accountId": 1, "userName": "Aaron Forrester", "balance": "1234.56"}

The frontend keeps that string, displays it with `Intl.NumberFormat`, and sends
amounts back as strings. It never does arithmetic on a balance; it renders the
one the server returned. This is a one-character change in each serializer and it
is the single most commonly missed step in the whole chain.

TWO THINGS ARE NEVER IN A RESPONSE
----------------------------------
`password_hash`, and any field the caller is not entitled to. Serializing by
naming each field explicitly - rather than dumping an object's `__dict__` - is
what makes that guarantee hold when someone adds a column later: a new field is
invisible to the API until somebody deliberately adds it here.

NAMING
------
Snake_case inside Python, camelCase on the wire, matching the brief's samples and
the convention a React client expects. The translation happens here and only here.
"""
from decimal import Decimal

from .models import Account, Transaction, User


def money(value: Decimal) -> str:
    """The rule from the module docstring, in one place.

    Plain `str(Decimal)`, not `format_money`: no thousands separators, no currency
    symbol. Grouping and symbols are presentation, they vary by locale, and a
    client that has to strip commas before parsing has been handed a worse string
    than it was given. `"1234.56"` is the interchange form; `"1,234.56"` is the
    display form and belongs in the browser.
    """
    return f"{value:.2f}"


def user_json(user: User) -> dict:
    """Public view of a user. Note which field is absent."""
    return {
        "userId": user.user_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "createdAt": user.created_at.isoformat(),
        # password_hash is deliberately not here, and never will be.
    }


def account_json(account: Account, owner: User | None = None) -> dict:
    """Public view of an account.

    `availableForWithdrawal` is included alongside `balance` because for a savings
    account they differ, and a client that computes "available" for itself would
    have to duplicate the minimum-balance rule. Sending both means the rule stays
    in one place - the `Account` subclass - and the UI can grey out the submit
    button without knowing why.
    """
    payload = {
        "accountId": account.account_id,
        "userId": account.user_id,
        "accountType": account.account_type,
        "status": account.status,
        "balance": money(account.balance),
        "availableForWithdrawal": money(account.available_for_withdrawal()),
        "minimumBalance": money(account.minimum_balance),
        "createdAt": account.created_at.isoformat(),
    }
    if owner is not None:
        # The brief's Account Response carries "userName", so it is here when the
        # caller has the owner to hand. Optional, because the common list endpoint
        # already knows every account belongs to the caller.
        payload["userName"] = owner.name
    return payload


def transaction_json(txn: Transaction) -> dict:
    """Public view of one ledger entry.

    `amount` is always positive and `direction` carries the sign, matching how the
    row is stored. `signedAmount` is supplied as well so a client can sum a page
    without re-deriving which types are credits - that mapping lives in
    `models.CREDIT_TYPES` and should not be copied into a frontend.
    """
    return {
        "txnId": txn.txn_id,
        "accountId": txn.account_id,
        "type": txn.txn_type,
        "amount": money(txn.amount),
        "signedAmount": money(txn.signed_amount),
        "direction": "CREDIT" if txn.signed_amount > 0 else "DEBIT",
        "clientTxnId": txn.client_txn_id,
        "createdAt": txn.created_at.isoformat(),
    }


def page_json(rows: list, total: int, page: int, page_size: int) -> dict:
    """Envelope for a paginated list.

    Paginated from the first day even though the seed data fits on one screen.
    Adding pagination later changes the response shape, which breaks every client
    that consumed the bare array, so the array is inside an envelope from the
    start and the cost of that decision is one word of nesting.
    """
    return {
        "items": rows,
        "page": page,
        "pageSize": page_size,
        "total": total,
        # Ceiling division without importing math: how many pages the client can ask for.
        "totalPages": (total + page_size - 1) // page_size if page_size else 0,
    }
