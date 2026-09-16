"""MongoDB storage. The same repository interface as `BankStore`, backed by Atlas.

    from bank import BankService
    from bank.mongo_store import MongoStore

    store = MongoStore()                  # reads MONGODB_URI / MONGODB_DB
    service = BankService(store)          # identical to the in-memory version

`services.py` cannot tell which store it was handed, which is the whole point of
`store.py` having been written as a class rather than as module-level dicts. The
business rules, the API, the serializers and the tests are untouched by this file
existing.

WHY THIS IS NOT IMPORTED BY `bank/__init__.py`
----------------------------------------------
Importing this module requires pymongo. The backend's promise is that it runs on
a clean machine with nothing installed, and `python server.py` still honours that
- Mongo is opt-in via `--mongo`, and the import happens inside that branch. A
teammate who has not done the Atlas setup is not blocked by someone else having.

THE FOUR THINGS THAT CHANGE SHAPE FROM `BankStore`
--------------------------------------------------
1. **Ids.** `itertools.count(1)` becomes a `counters` collection incremented with
   `find_one_and_update` + `$inc`, which is atomic on the server. We keep integer
   ids rather than adopting ObjectId because the API returns integers, the brief's
   samples show integers, and the Postman collection references specific numbers.

2. **Email uniqueness.** The `_email_index` dict becomes a unique index on
   `users.email`. The check is no longer code that can be forgotten; it is a
   constraint the server enforces for every writer.

3. **Idempotency.** The `_client_txn_ids` set becomes a unique, sparse index on
   `transactions.client_txn_id`. This is the one that genuinely gets *stronger*:
   a Python set protects one process, an index protects the database.

4. **Atomicity.** `threading.RLock` guards one process. `transaction()` opens a
   real MongoDB session, which is what makes `transfer()`'s four writes all-or-
   nothing when the server is not the only writer. This requires a replica set;
   Atlas M0 is one. See mongo.md.

MONEY
-----
Integer cents, stored as a BSON 64-bit integer. Deliberately **not** Decimal128,
which is what the older `seed_data_bank_app.md` planning document specifies - that
document predates the move to integer cents and its Mongo section would produce a
database this code refuses to read. `money.to_cents()` rejects anything that is
not an int, by design, so the failure is loud rather than a silent 100x error.
"""
import contextlib
import threading
from datetime import datetime, timezone

from . import config
from .errors import AccountNotFound, DuplicateTransaction, EmailAlreadyUsed, UserNotFound
from .models import ACTIVE, CREDIT_TYPES, Account, Transaction, User, make_account

USERS = "users"
ACCOUNTS = "accounts"
TRANSACTIONS = "transactions"
COUNTERS = "counters"


def _utc(value) -> datetime:
    """Re-attach UTC to a datetime read back from MongoDB.

    BSON stores an instant, and pymongo hands it back as a *naive* datetime by
    default. Our models are timezone-aware, and `serializers` calls `.isoformat()`
    on them - so without this, a document round-trip silently drops the `+00:00`
    and the API starts emitting timestamps with no zone. A client parsing those
    as local time is off by however many hours it happens to be.
    """
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class MongoStore:
    """Repository over a MongoDB database. Method-for-method with `BankStore`."""

    def __init__(self, uri: str | None = None, db_name: str | None = None,
                 client=None, ensure_indexes: bool = True):
        from pymongo import MongoClient

        uri = uri or config.mongo_uri()
        if not uri:
            raise RuntimeError(
                "MONGODB_URI is not set. Copy .env.example to .env and fill it "
                "in - see mongo.md, or run `python tools/check_mongo.py`."
            )
        # One client per process, shared. pymongo's client owns a connection pool
        # and is thread-safe; constructing one per request would exhaust M0's
        # 500-connection limit almost immediately.
        self._client = client or MongoClient(uri, appName="simple-bank")
        self.db = self._client[db_name or config.mongo_db_name()]

        # The session for the transaction currently in progress, if any. Thread
        # local because api.py serves requests on a thread pool and a ClientSession
        # must not be used from two threads at once.
        self._local = threading.local()

        if ensure_indexes:
            self.ensure_indexes()

    # ------------------------------------------------------------- setup

    def ensure_indexes(self) -> None:
        """Create the indexes that enforce rules. Safe to call on every start.

        `create_index` is idempotent, so this belongs in code rather than in
        something a person clicks once in the Atlas UI - an index that exists on
        one teammate's cluster and not in the repository is a rule that silently
        does not apply to everyone else.

        Two of these are not performance tuning. They are the storage-level
        versions of business rules that `BankStore` implements in Python.
        """
        # The UNIQUE constraint behind add_user()'s duplicate-email rejection.
        self._create_index(USERS, "email", unique=True, name="uq_user_email")

        # The idempotency guarantee. `sparse` because most transactions have no
        # client id, and without it every such document would collide on null.
        self._create_index(TRANSACTIONS, "client_txn_id",
                           unique=True, sparse=True, name="uq_client_txn")

        # History is always "this account, newest first" - see
        # transactions_for_account, which sorts on _id descending. The sort key
        # must be `_id` and not `txn_id`: the transaction's id IS the document's
        # `_id`, so there is no `txn_id` field to index and an index naming one
        # would be built, reported by Atlas, and never used by any query.
        self._create_index(TRANSACTIONS, [("account_id", 1), ("_id", -1)],
                           name="ix_txn_account_recent")
        self._create_index(ACCOUNTS, "user_id", name="ix_account_user")

    def _create_index(self, collection: str, keys, **options) -> None:
        """create_index, tolerant of an equivalent index someone already made.

        `create_index` is idempotent only for an *exact* match. If the same keys
        already exist under a different name - because a teammate made one by
        hand in the Atlas UI, or an earlier version of this file used a different
        name - the server raises IndexOptionsConflict (85) and, without this,
        every `MongoStore(...)` against that database would fail at construction.

        That is a real scenario on a shared cluster rather than a hypothetical
        one, and the right response is to accept the index that is already doing
        the job. A genuine conflict - same name, different keys (86) - is not
        papered over: the old index is dropped and replaced, because there the
        two definitions actually disagree and ours is the one in version control.
        """
        from pymongo.errors import DuplicateKeyError, OperationFailure

        try:
            self.db[collection].create_index(keys, **options)
        except DuplicateKeyError as exc:
            # A unique index cannot be built because the data already violates
            # it. Failing loudly is right - the alternative is a server that
            # starts up believing a rule is enforced when it is not - but the
            # server's own message does not say what to do about it.
            detail = exc.details.get("errmsg", exc) if exc.details else exc
            raise RuntimeError(
                f"Cannot create the unique index {options.get('name')!r} on "
                f"{self.db.name}.{collection}: the existing data already "
                f"breaks it.\n"
                f"  {detail}\n"
                "  This usually means the collection holds rows written by an "
                "older schema.\n"
                "  Re-seed it:  python tools/seed_mongo.py --reset"
            ) from None
        except OperationFailure as exc:
            if exc.code == 85:      # IndexOptionsConflict: same keys, other name
                return
            if exc.code == 86:      # IndexKeySpecsConflict: same name, other keys
                self.db[collection].drop_index(options["name"])
                self.db[collection].create_index(keys, **options)
                return
            raise

    def drop_everything(self) -> None:
        """Wipe the database. Used by the seeder's --reset and by nothing else."""
        for name in (USERS, ACCOUNTS, TRANSACTIONS, COUNTERS):
            self.db.drop_collection(name)

    # -------------------------------------------------------- transactions

    @property
    def _session(self):
        return getattr(self._local, "session", None)

    @contextlib.contextmanager
    def transaction(self):
        """Run the enclosed writes as one MongoDB transaction.

        Re-entrant: `transfer()` calls the same guarded internals as `withdraw`,
        and nesting `start_transaction` raises. The inner `with` therefore joins
        the outer one rather than opening a second, which mirrors why the service
        layer uses an RLock rather than a Lock.
        """
        if self._session is not None:
            yield self._session          # already inside one; join it
            return

        with self._client.start_session() as session:
            self._local.session = session
            try:
                with session.start_transaction():
                    yield session
            finally:
                self._local.session = None

    def _kw(self) -> dict:
        """Pass the active session to a pymongo call, when there is one.

        Every read and write goes through this. A write that forgets it silently
        lands outside the transaction and is not rolled back with the rest, which
        is the single easiest way to break atomicity here.
        """
        session = self._session
        return {"session": session} if session is not None else {}

    def _next_id(self, name: str) -> int:
        """Allocate an id. The `counters` collection is AUTO_INCREMENT.

        `find_one_and_update` with `$inc` and `upsert` is one atomic server-side
        operation, so two processes allocating at the same moment get different
        numbers. Reading a max and adding one would not be safe.
        """
        doc = self.db[COUNTERS].find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,          # ReturnDocument.AFTER
            **self._kw(),
        )
        return int(doc["seq"])

    # -------------------------------------------------------------- users

    def _user_from_doc(self, doc: dict) -> User:
        user = User(
            user_id=doc["_id"],
            name=doc["name"],
            email=doc["email"],
            role=doc.get("role", "CUSTOMER"),
            password_hash=doc.get("password_hash"),
        )
        user.created_at = _utc(doc.get("created_at"))
        return user

    def add_user(self, name: str, email: str, role: str = "CUSTOMER",
                 password_hash: str | None = None) -> User:
        """Insert a user, rejecting a duplicate email.

        The rejection comes from the unique index rather than from a lookup here.
        A check-then-insert would leave a window in which two requests both find
        the address free, and the index closes it.
        """
        from pymongo.errors import DuplicateKeyError

        key = email.strip().lower()
        user = User(user_id=self._next_id("user_id"), name=name, email=key,
                    role=role, password_hash=password_hash)
        try:
            self.db[USERS].insert_one({
                "_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "password_hash": user.password_hash,
                "created_at": user.created_at,
            }, **self._kw())
        except DuplicateKeyError:
            raise EmailAlreadyUsed(f"email already registered: {key}") from None
        return user

    def get_user(self, user_id: int) -> User:
        doc = self.db[USERS].find_one({"_id": user_id}, **self._kw())
        if doc is None:
            raise UserNotFound(f"no user with id {user_id}")
        return self._user_from_doc(doc)

    def find_user_by_email(self, email: str) -> User | None:
        doc = self.db[USERS].find_one({"email": email.strip().lower()}, **self._kw())
        return self._user_from_doc(doc) if doc else None

    def all_users(self) -> list[User]:
        rows = self.db[USERS].find(**self._kw()).sort("_id", 1)
        return [self._user_from_doc(d) for d in rows]

    # ----------------------------------------------------------- accounts

    def _account_from_doc(self, doc: dict) -> Account:
        """Rebuild the right Account subclass from a document.

        Goes through `make_account`, so `ACCOUNT_TYPES` stays the single place
        that maps a type string to a class and a new account type needs no edit
        here. The balance is assigned to `_balance` directly and deliberately:
        `balance` is a read-only property with no setter, and reconstructing a
        stored row is not the same act as applying a transaction to it.
        """
        account = make_account(doc["account_type"], user_id=doc["user_id"])
        account.account_id = doc["_id"]
        account._balance = int(doc["balance"])
        account.status = doc.get("status", ACTIVE)
        account.created_at = _utc(doc.get("created_at"))
        return account

    def _account_doc(self, account: Account) -> dict:
        return {
            "_id": account.account_id,
            "user_id": account.user_id,
            "account_type": account.account_type,
            "balance": int(account.balance),
            "status": account.status,
            "created_at": account.created_at,
        }

    def add_account(self, account: Account) -> Account:
        if account.account_id is None:
            account.account_id = self._next_id("account_id")
        self.db[ACCOUNTS].insert_one(self._account_doc(account), **self._kw())
        return account

    def get_account(self, account_id: int) -> Account:
        doc = self.db[ACCOUNTS].find_one({"_id": account_id}, **self._kw())
        if doc is None:
            raise AccountNotFound(f"no account with id {account_id}")
        return self._account_from_doc(doc)

    def save_account(self, account: Account) -> Account:
        """Write back an account the service layer just changed.

        This method is why `BankStore` grew a no-op version of it. There,
        `get_account` returns the object in the dict and mutating it *is* the
        save. Here it returns a fresh object built from a document, so without
        this call a deposit would update a balance in memory and nothing on the
        server - and every test would still pass, because the in-memory store
        does not need it.
        """
        self.db[ACCOUNTS].update_one(
            {"_id": account.account_id},
            {"$set": {"balance": int(account.balance), "status": account.status}},
            **self._kw(),
        )
        return account

    def accounts_for_user(self, user_id: int) -> list[Account]:
        rows = self.db[ACCOUNTS].find({"user_id": user_id}, **self._kw()).sort("_id", 1)
        return [self._account_from_doc(d) for d in rows]

    def all_accounts(self) -> list[Account]:
        rows = self.db[ACCOUNTS].find(**self._kw()).sort("_id", 1)
        return [self._account_from_doc(d) for d in rows]

    # ------------------------------------------------------- transactions

    def _txn_from_doc(self, doc: dict) -> Transaction:
        return Transaction(
            txn_id=doc["_id"],
            account_id=doc["account_id"],
            txn_type=doc["txn_type"],
            amount=int(doc["amount"]),
            client_txn_id=doc.get("client_txn_id"),
            created_at=_utc(doc.get("created_at")),
            adjusted_by=doc.get("adjusted_by"),
            reason=doc.get("reason"),
        )

    def next_txn_id(self) -> int:
        return self._next_id("txn_id")

    def client_txn_id_seen(self, client_txn_id: str | None) -> bool:
        """Fast path for the idempotency guard.

        This is a lookup, so between it and the insert there is a window. That is
        acceptable because it is not the actual protection: the unique index on
        `client_txn_id` is, and `add_transaction` turns its violation into the
        same `DuplicateTransaction` this would have raised. This exists to give
        the common case a clean error instead of an index violation.
        """
        if client_txn_id is None:
            return False
        return self.db[TRANSACTIONS].find_one(
            {"client_txn_id": client_txn_id}, {"_id": 1}, **self._kw()) is not None

    def add_transaction(self, txn: Transaction) -> Transaction:
        from pymongo.errors import DuplicateKeyError

        doc = {
            "_id": txn.txn_id,
            "account_id": txn.account_id,
            "txn_type": txn.txn_type,
            "amount": int(txn.amount),
            "created_at": txn.created_at,
        }
        # Omitted rather than stored as null, so the sparse unique index does not
        # have to consider these documents at all.
        if txn.client_txn_id is not None:
            doc["client_txn_id"] = txn.client_txn_id
        if txn.adjusted_by is not None:
            doc["adjusted_by"] = txn.adjusted_by
            doc["reason"] = txn.reason

        try:
            self.db[TRANSACTIONS].insert_one(doc, **self._kw())
        except DuplicateKeyError:
            # The index caught a replay that slipped past client_txn_id_seen.
            raise DuplicateTransaction(
                f"transaction {txn.client_txn_id} has already been submitted"
            ) from None
        return txn

    def transactions_for_account(self, account_id: int,
                                 txn_type: str | None = None) -> list[Transaction]:
        query: dict = {"account_id": account_id}
        if txn_type:
            query["txn_type"] = txn_type
        rows = self.db[TRANSACTIONS].find(query, **self._kw()).sort("_id", -1)
        return [self._txn_from_doc(d) for d in rows]

    def ledger_sum(self, account_id: int) -> int:
        """Reconciliation, in cents, computed by the server.

        The credit/debit split is expressed with `$cond` over `CREDIT_TYPES`
        rather than hardcoding the type names, so `models.py` stays the single
        source of truth for which types add and which subtract.

        Returns an int. The amounts are BSON 64-bit integers and `$sum` over them
        is exact - which is the entire reason money is stored as cents rather
        than as the Decimal128 the older planning document specified.
        """
        pipeline = [
            {"$match": {"account_id": account_id}},
            {"$group": {
                "_id": None,
                "total": {"$sum": {
                    "$cond": [
                        {"$in": ["$txn_type", sorted(CREDIT_TYPES)]},
                        "$amount",
                        {"$multiply": ["$amount", -1]},
                    ]
                }},
            }},
        ]
        result = list(self.db[TRANSACTIONS].aggregate(pipeline, **self._kw()))
        return int(result[0]["total"]) if result else 0

    # ------------------------------------------------------------- admin

    def close(self) -> None:
        self._client.close()

    def stats(self) -> dict[str, int]:
        """Row counts, for the server's startup banner."""
        return {
            "users": self.db[USERS].count_documents({}),
            "accounts": self.db[ACCOUNTS].count_documents({}),
            "transactions": self.db[TRANSACTIONS].count_documents({}),
        }
