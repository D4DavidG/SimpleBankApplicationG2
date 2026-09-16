"""In-memory repository.

Holds everything in dictionaries and lists. The test suites and the console demo
use it, because it needs no network and starts clean every run.

The server uses mongo_store.MongoStore instead when a MongoDB connection string
is configured. Both classes have the same method names, and that is the whole
design: the service layer talks to these names and never to a dictionary or a
collection directly, so neither the rules in services.py nor the routes in api.py
know which store they were given.
"""
import itertools
import threading
from contextlib import contextmanager

from .errors import AccountNotFound, EmailAlreadyUsed, UserNotFound
from .models import Account, Transaction, User


class BankStore:
    def __init__(self):
        self._users: dict[int, User] = {}
        self._email_index: dict[str, int] = {}
        self._accounts: dict[int, Account] = {}
        self._transactions: list[Transaction] = []
        self._audit: list[tuple] = []
        # Identity sequences. These stand in for AUTO_INCREMENT, and living here
        # rather than on the model classes is what makes two BankStore instances
        # genuinely independent - each numbers its own rows from 1.
        self._user_ids = itertools.count(1)
        self._account_ids = itertools.count(1)
        self._txn_ids = itertools.count(1)
        self._client_txn_ids: set[str] = set()
        # Stands in for a database transaction. The service layer runs every
        # change inside atomic(), so two threads cannot interleave a balance check
        # and the write it guards. Reentrant, because one service method can call
        # another that also opens an atomic block.
        self._lock = threading.RLock()

    # ---- units of work ----

    @contextmanager
    def atomic(self):
        """Run a group of reads and writes as one unit.

        Here that is a lock, and it is enough: changes are made to the stored
        objects directly, so there is never a half-written copy to roll back.
        MongoStore.atomic() gives the same guarantee with a real transaction.
        """
        with self._lock:
            yield

    # ---- users ----

    def add_user(self, name: str, email: str, role: str = "CUSTOMER",
                 password_hash: str | None = None) -> User:
        """Insert a user, rejecting a duplicate email.

        `_email_index` is this class standing in for the `UNIQUE` index on
        `users.email`. MongoStore gets the same guarantee from a real unique index.
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

    def accounts_for_user(self, user_id: int) -> list[Account]:
        return sorted(
            (a for a in self._accounts.values() if a.user_id == user_id),
            key=lambda a: a.account_id,
        )

    def all_accounts(self) -> list[Account]:
        return sorted(self._accounts.values(), key=lambda a: a.account_id)

    def save_balance(self, account: Account) -> None:
        """Persist a balance changed by Account._apply.

        Nothing to do here: the object the service changed is the stored record.
        MongoStore has to write it back, which is why the service always calls it.
        """

    def save_status(self, account: Account) -> None:
        """Persist a status change such as a freeze. Nothing to do here, as above."""

    # ---- transactions ----

    def next_txn_id(self) -> int:
        return next(self._txn_ids)

    def client_txn_id_seen(self, client_txn_id: str | None) -> bool:
        """Idempotency check. Stands in for the unique index MongoStore uses."""
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

    # ---- audit log ----

    def add_audit_entry(self, actor_user_id: int, action: str,
                        account_id: int | None, reason: str) -> None:
        self._audit.append((actor_user_id, action, account_id, reason))

    def audit_entries(self) -> list[tuple]:
        """Oldest first, as a copy, so a caller cannot append by holding the list."""
        return list(self._audit)
