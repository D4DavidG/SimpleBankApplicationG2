"""In-memory storage.

No database today. This class holds everything in dictionaries and lists.

It is written as a repository on purpose: the service layer talks to these method
names and never to a dictionary directly. When MySQL or MongoDB arrives later in
the week, this file is the only one that gets rewritten and the business rules in
services.py do not change at all. That is the same reason the class exists as a
seam rather than the services just using globals.
"""
import contextlib
import itertools

from .errors import AccountNotFound, EmailAlreadyUsed, UserNotFound
from .models import Account, Transaction, User


class BankStore:
    def __init__(self):
        self._users: dict[int, User] = {}
        self._email_index: dict[str, int] = {}
        self._accounts: dict[int, Account] = {}
        self._transactions: list[Transaction] = []
        # Identity sequences. These stand in for AUTO_INCREMENT, and living here
        # rather than on the model classes is what makes two BankStore instances
        # genuinely independent - each numbers its own rows from 1.
        self._user_ids = itertools.count(1)
        self._account_ids = itertools.count(1)
        self._txn_ids = itertools.count(1)
        self._client_txn_ids: set[str] = set()

    # ---- users ----

    def add_user(self, name: str, email: str, role: str = "CUSTOMER",
                 password_hash: str | None = None) -> User:
        """Insert a user, rejecting a duplicate email.

        `_email_index` is this class standing in for the `UNIQUE` index on
        `users.email` that the database will provide. Keeping the uniqueness check
        here rather than in the service layer is deliberate: it is a storage
        constraint, and when MySQL arrives the index enforces it for free and this
        method shrinks to an INSERT.
        """
        key = email.strip().lower()
        if key in self._email_index:
            raise EmailAlreadyUsed(f"email already registered: {key}")
        user = User(user_id=next(self._user_ids), name=name, email=key, role=role,
                    password_hash=password_hash)
        self._users[user.user_id] = user
        self._email_index[key] = user.user_id
        return user

    def get_user(self, user_id: int) -> User:
        try:
            return self._users[user_id]
        except KeyError:
            raise UserNotFound(f"no user with id {user_id}") from None

    def find_user_by_email(self, email: str) -> User | None:
        user_id = self._email_index.get(email.strip().lower())
        return self._users.get(user_id) if user_id is not None else None

    def all_users(self) -> list[User]:
        return sorted(self._users.values(), key=lambda u: u.user_id)

    # ---- accounts ----

    def add_account(self, account: Account) -> Account:
        """Insert an account, assigning its id.

        The account arrives with `account_id` set to None and leaves with a number.
        That is the INSERT ... AUTO_INCREMENT step made explicit, and it is the
        reason `make_account()` does not try to number anything itself.
        """
        if account.account_id is None:
            account.account_id = next(self._account_ids)
        self._accounts[account.account_id] = account
        return account

    def get_account(self, account_id: int) -> Account:
        try:
            return self._accounts[account_id]
        except KeyError:
            raise AccountNotFound(f"no account with id {account_id}") from None

    def save_account(self, account: Account) -> Account:
        """Persist an account whose fields the service layer just changed.

        A no-op here, and deliberately not removed as dead code. `get_account`
        returns the very object held in `_accounts`, so mutating it *is* the
        save - but that is a property of storing objects in a dict, not a
        property of storage in general. A database store hands back a fresh
        object built from a document, and a mutation to that object reaches
        nothing unless somebody writes it back.

        So the service layer calls this after every change to an account, and in
        memory it costs an attribute lookup. Without it, `MongoStore` would need
        `services.py` to be written differently from the version the tests
        exercise, which is exactly the coupling the repository pattern is here
        to prevent.
        """
        self._accounts[account.account_id] = account
        return account

    @contextlib.contextmanager
    def transaction(self):
        """Group writes so they all happen or none do.

        Nothing to do in memory: no other thread can interleave, because
        `BankService` holds an RLock across every method that moves money, and
        nothing here can fail partway and leave a half-written dict.

        It exists so `services.transfer()` can declare the boundary it needs in
        one place. `MongoStore` implements this with a real session, which is the
        version that holds when the process is not the only writer.
        """
        yield

    def accounts_for_user(self, user_id: int) -> list[Account]:
        return sorted(
            (a for a in self._accounts.values() if a.user_id == user_id),
            key=lambda a: a.account_id,
        )

    def all_accounts(self) -> list[Account]:
        return sorted(self._accounts.values(), key=lambda a: a.account_id)

    # ---- transactions ----

    def next_txn_id(self) -> int:
        return next(self._txn_ids)

    def client_txn_id_seen(self, client_txn_id: str | None) -> bool:
        """Idempotency check. Stands in for the UNIQUE index the database will
        provide once there is a database."""
        return client_txn_id is not None and client_txn_id in self._client_txn_ids

    def add_transaction(self, txn: Transaction) -> Transaction:
        self._transactions.append(txn)
        if txn.client_txn_id:
            self._client_txn_ids.add(txn.client_txn_id)
        return txn

    def transactions_for_account(self, account_id: int,
                                 txn_type: str | None = None) -> list[Transaction]:
        rows = [t for t in self._transactions if t.account_id == account_id]
        if txn_type:
            rows = [t for t in rows if t.txn_type == txn_type]
        return sorted(rows, key=lambda t: t.txn_id, reverse=True)

    def ledger_sum(self, account_id: int) -> int:
        """Reconciliation, in cents. Must equal the account's stored balance.

        Integer addition, so this is exact and `==` against the stored balance
        needs no tolerance.
        """
        total = 0
        for txn in self._transactions:
            if txn.account_id == account_id:
                total += txn.signed_amount
        return total
