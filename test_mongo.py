"""The business rules, run against a real MongoDB cluster.

    python test_mongo.py
    python -m unittest test_mongo -v

SKIPPED unless `MONGODB_URI` is set (in `.env` or the environment) and pymongo is
installed. That is deliberate: `test_bank.py` and `test_api.py` must keep running
on a clean machine with nothing installed, and a teammate who has not done the
Atlas setup should see a skip, not a failure.

WHY THIS FILE EXISTS WHEN test_bank.py ALREADY PASSES
-----------------------------------------------------
`test_bank.py` proves the rules hold against `BankStore`. It cannot prove they
hold against `MongoStore`, and the difference is not theoretical - the whole
class of bug this file exists to catch is the one where an object is mutated in
memory and never written back. Every one of those bugs passes `test_bank.py`,
because the in-memory store's `save_account` is a no-op it does not need.

So these tests re-assert the rules, and then re-read from the database rather
than trusting the object in hand. `_reload()` below is the point of the file.

IT USES ITS OWN DATABASE
------------------------
`simple_bank_test`, or `$MONGODB_TEST_DB`. Never `MONGODB_DB`, because that is
whatever the developer is working against and this file drops collections. The
guard in setUpClass refuses to run against a database whose name does not end in
`_test`.
"""
import os
import unittest

from bank import (
    AccountNotActive, AccountNotFound, BankService, DuplicateTransaction,
    InsufficientFunds, NotAuthorized, config,
)

config.load_env()

MONGO_URI = os.environ.get("MONGODB_URI")
TEST_DB = os.environ.get("MONGODB_TEST_DB", "simple_bank_test")

# Test for pymongo itself, not for the MongoStore import. `mongo_store` imports
# pymongo inside MongoStore.__init__ rather than at module level - that is what
# keeps pymongo optional for everyone else - so importing the class succeeds on a
# machine that cannot use it, and the failure would land in setUp as 21 errors
# instead of 21 skips.
try:
    import pymongo  # noqa: F401
    PYMONGO = True
except ImportError:
    PYMONGO = False

if PYMONGO:
    from bank.mongo_store import MongoStore

SKIP_REASON = (
    "no MONGODB_URI (see mongo.md)" if not MONGO_URI
    else "pymongo not installed" if not PYMONGO
    else None
)


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class MongoTestCase(unittest.TestCase):
    """Base: a clean database per test, and a helper that re-reads from it."""

    @classmethod
    def setUpClass(cls):
        # A test suite that drops collections must never be pointed at the
        # database someone is demoing from. The name is the safety catch.
        if not TEST_DB.endswith("_test"):
            raise unittest.SkipTest(
                f"refusing to run destructive tests against {TEST_DB!r}: "
                "the test database name must end in '_test'"
            )
        cls.store_cls = MongoStore

    # One PBKDF2 hash for the whole suite. Deriving one costs ~0.6s by design,
    # and three users per test across twenty-one tests is a minute of the run
    # spent proving nothing. This is the same trick seed.py uses and for the same
    # reason: the hashing is not what these tests are about.
    _SHARED_HASH = None

    @classmethod
    def _demo_hash(cls):
        if MongoTestCase._SHARED_HASH is None:
            from bank import hash_password
            MongoTestCase._SHARED_HASH = hash_password("hunter2!!")
        return MongoTestCase._SHARED_HASH

    def setUp(self):
        # ensure_indexes=False on the way in, then drop, then index. The order
        # matters: this database is shared and may hold rows from an older schema
        # (it did - documents with an explicit client_txn_id of null, which the
        # sparse unique index cannot be built over). Indexing before wiping makes
        # the suite fail on somebody else's leftover data.
        self.store = MongoStore(db_name=TEST_DB, ensure_indexes=False)
        self.store.drop_everything()
        self.store.ensure_indexes()
        self.svc = BankService(self.store)
        pw = self._demo_hash()
        self.alice = self.svc.register_user("Alice", "alice@example.com",
                                            password_hash=pw)
        self.bob = self.svc.register_user("Bob", "bob@example.com",
                                          password_hash=pw)
        self.admin = self.svc.register_user("Admin", "admin@example.com",
                                            role="ADMIN", password_hash=pw)

    def tearDown(self):
        self.store.drop_everything()
        self.store.close()

    def _reload(self, account_id):
        """Read an account back out of MongoDB, bypassing anything in memory.

        Every assertion about a balance goes through this. Asserting on the
        object the service returned would pass even if nothing was ever written,
        which is the entire class of bug this file is here to catch.

        The client is closed straight afterwards. An M0 cluster allows 500
        connections and each MongoClient opens a pool, so a helper called several
        times per test that leaked one would eventually take the cluster out from
        under the rest of the suite.
        """
        other = MongoStore(db_name=TEST_DB, ensure_indexes=False)
        try:
            return other.get_account(account_id)
        finally:
            other.close()


class TestPersistence(MongoTestCase):
    """The bugs that only exist once storage is not a dict."""

    def test_deposit_is_actually_written_to_the_database(self):
        acct = self.svc.open_account(self.alice, "CHECKING")
        self.svc.deposit(acct.account_id, 10000, self.alice)
        self.assertEqual(self._reload(acct.account_id).balance, 10000)

    def test_withdrawal_is_actually_written_to_the_database(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        self.svc.withdraw(acct.account_id, 2500, self.alice)
        self.assertEqual(self._reload(acct.account_id).balance, 7500)

    def test_opening_balance_is_written_with_its_ledger_entry(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 5000)
        self.assertEqual(self._reload(acct.account_id).balance, 5000)
        self.assertEqual(self.store.ledger_sum(acct.account_id), 5000)

    def test_freeze_is_persisted(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 1000)
        self.svc.set_frozen(acct.account_id, True, "suspected fraud on the account",
                            self.admin)
        self.assertEqual(self._reload(acct.account_id).status, "FROZEN")

    def test_money_is_stored_as_an_integer_not_a_float_or_decimal(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 123456)
        doc = self.store.db["accounts"].find_one({"_id": acct.account_id})
        self.assertIsInstance(doc["balance"], int)
        self.assertNotIsInstance(doc["balance"], bool)
        self.assertEqual(doc["balance"], 123456)

    def test_timestamps_come_back_timezone_aware(self):
        acct = self.svc.open_account(self.alice, "CHECKING")
        self.assertIsNotNone(self._reload(acct.account_id).created_at.tzinfo)
        self.assertIsNotNone(self.store.get_user(self.alice.user_id).created_at.tzinfo)


class TestRulesHoldAgainstMongo(MongoTestCase):
    """The same rules test_bank.py asserts, re-asserted against the database."""

    def test_cannot_withdraw_more_than_the_balance(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 1250)
        with self.assertRaises(InsufficientFunds):
            self.svc.withdraw(acct.account_id, 1251, self.alice)
        self.assertEqual(self._reload(acct.account_id).balance, 1250)

    def test_frozen_account_rejects_movement(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        self.svc.set_frozen(acct.account_id, True, "a written reason of some length",
                            self.admin)
        with self.assertRaises(AccountNotActive):
            self.svc.deposit(acct.account_id, 100, self.alice)
        self.assertEqual(self._reload(acct.account_id).balance, 10000)

    def test_cannot_read_another_users_account(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        with self.assertRaises(AccountNotFound):
            self.svc.get_account_for(acct.account_id, self.bob)

    def test_duplicate_email_is_refused_by_the_unique_index(self):
        from bank import EmailAlreadyUsed
        with self.assertRaises(EmailAlreadyUsed):
            self.svc.register_user("Impostor", "alice@example.com", password="x!23456y")

    def test_admin_cannot_move_money_through_the_customer_route(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        with self.assertRaises(AccountNotFound):
            self.svc.withdraw(acct.account_id, 100, self.admin)

    def test_adjustment_writes_a_ledger_entry_and_reconciles(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        self.svc.adjust(acct.account_id, 500, "CREDIT",
                        "correcting a mis-posted fee", self.admin)
        reloaded = self._reload(acct.account_id)
        self.assertEqual(reloaded.balance, 10500)
        self.assertEqual(self.store.ledger_sum(acct.account_id), 10500)

    def test_non_admin_cannot_adjust(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        with self.assertRaises(NotAuthorized):
            self.svc.adjust(acct.account_id, 500, "CREDIT",
                            "trying it on, with a reason", self.alice)


class TestIdempotency(MongoTestCase):
    """The unique index is the guarantee, not the Python set."""

    def test_replayed_client_txn_id_is_refused(self):
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        self.svc.deposit(acct.account_id, 500, self.alice, client_txn_id="abc-123")
        with self.assertRaises(DuplicateTransaction):
            self.svc.deposit(acct.account_id, 500, self.alice, client_txn_id="abc-123")
        self.assertEqual(self._reload(acct.account_id).balance, 10500)

    def test_the_index_refuses_a_replay_even_bypassing_the_service_check(self):
        """The real test: insert straight into the store, skipping the lookup.

        `client_txn_id_seen` is a lookup with a window after it. If the index
        were missing or not unique, this second insert would succeed and the
        idempotency rule would hold only for requests that happened to be far
        enough apart.
        """
        from bank.models import Transaction
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        self.store.add_transaction(Transaction(
            txn_id=self.store.next_txn_id(), account_id=acct.account_id,
            txn_type="DEPOSIT", amount=100, client_txn_id="race-1"))
        with self.assertRaises(DuplicateTransaction):
            self.store.add_transaction(Transaction(
                txn_id=self.store.next_txn_id(), account_id=acct.account_id,
                txn_type="DEPOSIT", amount=100, client_txn_id="race-1"))

    def test_transactions_without_a_client_id_do_not_collide(self):
        """The sparse half of the index. Without `sparse`, the second of these
        would collide on a null key and ordinary deposits would fail."""
        acct = self.svc.open_account(self.alice, "CHECKING", 10000)
        for _ in range(3):
            self.svc.deposit(acct.account_id, 100, self.alice)
        self.assertEqual(self._reload(acct.account_id).balance, 10300)


class TestTransferAtomicity(MongoTestCase):
    """The reason the cluster has to be a replica set."""

    def test_transfer_moves_money_and_both_legs_persist(self):
        src = self.svc.open_account(self.alice, "CHECKING", 10000)
        dst = self.svc.open_account(self.bob, "CHECKING", 0)
        self.svc.transfer(src.account_id, dst.account_id, 2500, self.alice)
        self.assertEqual(self._reload(src.account_id).balance, 7500)
        self.assertEqual(self._reload(dst.account_id).balance, 2500)
        self.assertEqual(self.store.ledger_sum(src.account_id), 7500)
        self.assertEqual(self.store.ledger_sum(dst.account_id), 2500)

    def test_a_failure_mid_transfer_rolls_back_both_legs(self):
        """The guarantee, tested by forcing a failure between the two writes.

        Without a real transaction the debit would already be committed when the
        credit fails, and the money would simply be gone - the balance down, no
        matching entry anywhere, and reconciliation broken permanently.
        """
        src = self.svc.open_account(self.alice, "CHECKING", 10000)
        dst = self.svc.open_account(self.bob, "CHECKING", 0)

        boom = RuntimeError("simulated failure between the two legs")
        real_add = self.store.add_transaction
        calls = []

        def failing_add(txn):
            calls.append(txn)
            if len(calls) == 2:          # let TRANSFER_OUT land, fail on TRANSFER_IN
                raise boom
            return real_add(txn)

        self.store.add_transaction = failing_add
        with self.assertRaises(RuntimeError):
            self.svc.transfer(src.account_id, dst.account_id, 2500, self.alice)
        self.store.add_transaction = real_add

        self.assertEqual(self._reload(src.account_id).balance, 10000,
                         "the debit was not rolled back")
        self.assertEqual(self._reload(dst.account_id).balance, 0,
                         "the credit was not rolled back")

        # Not "no entries at all": opening the account with a balance wrote a
        # legitimate DEPOSIT, and that one is supposed to still be here. What
        # must not have survived is either leg of the abandoned transfer.
        legs = [t for t in self.store.transactions_for_account(src.account_id)
                if t.txn_type.startswith("TRANSFER")]
        self.assertEqual(legs, [], "a transfer leg survived the rollback")
        self.assertEqual(self.store.transactions_for_account(dst.account_id), [],
                         "the credited account kept an entry from a rolled-back transfer")

        # The invariant, which is what all of the above is protecting.
        self.assertEqual(self.svc.reconcile_all(), [])

    def test_reconciliation_holds_across_a_batch_of_operations(self):
        src = self.svc.open_account(self.alice, "CHECKING", 50000)
        dst = self.svc.open_account(self.bob, "SAVINGS", 10000)
        for i in range(5):
            self.svc.deposit(src.account_id, 100 * (i + 1), self.alice)
            self.svc.withdraw(src.account_id, 50, self.alice)
            self.svc.transfer(src.account_id, dst.account_id, 250, self.alice)
        self.assertEqual(self.svc.reconcile_all(), [])


class TestIdAllocation(MongoTestCase):
    """The `counters` collection standing in for AUTO_INCREMENT."""

    def test_ids_are_sequential_integers_from_one(self):
        a = self.svc.open_account(self.alice, "CHECKING")
        b = self.svc.open_account(self.alice, "SAVINGS")
        self.assertEqual((a.account_id, b.account_id), (1, 2))
        self.assertIsInstance(a.account_id, int)

    def test_ids_are_not_reused_after_a_reconnect(self):
        self.svc.open_account(self.alice, "CHECKING")
        other = MongoStore(db_name=TEST_DB, ensure_indexes=False)
        try:
            acct = BankService(other).open_account(self.alice, "SAVINGS")
            self.assertEqual(acct.account_id, 2)
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
