"""Tests for the bank core. Standard library only.

    python3 -m unittest -v

No pytest, no database, no server. Every test is a function call, which is the
payoff for keeping the rules in services.py free of framework imports.
"""
from decimal import Decimal
import unittest

from bank import (
    AccountNotActive, AccountNotFound, BankService, BankStore,
    DuplicateTransaction, InsufficientFunds, InvalidAmount, NotAuthorized,
    SavingsAccount, format_money, parse_amount, to_money,
)


class BankTestCase(unittest.TestCase):
    """Shared fixture: two customers, one admin, three accounts."""

    def setUp(self):
        self.store = BankStore()
        self.svc = BankService(self.store)
        self.aaron = self.svc.register_user("Aaron Forrester", "aaron.forrester@example.com")
        self.erik = self.svc.register_user("Erik Mayes", "erik.mayes@example.com")
        self.david = self.svc.register_user("David Gusmao", "david.gusmao@example.com",
                                            role="ADMIN")
        self.a_checking = self.svc.open_account(self.aaron, "CHECKING", "12.50")
        self.a_savings = self.svc.open_account(self.aaron, "SAVINGS", "500.00")
        self.e_checking = self.svc.open_account(self.erik, "CHECKING", "84210.75")

    def tearDown(self):
        """Every test ends with the ledger reconciling. If a rule ever changes a
        balance without writing an entry, whichever test exercised it fails here
        rather than silently passing."""
        self.assertEqual(self.svc.reconcile_all(), [],
                         "balance and ledger disagree after this test")


# --------------------------------------------------------------- money handling

class TestMoney(unittest.TestCase):
    def test_float_is_rejected_not_rounded(self):
        with self.assertRaises(TypeError):
            to_money(12.50)
        with self.assertRaises(InvalidAmount):
            parse_amount(12.50)

    def test_decimal_arithmetic_is_exact_where_float_is_not(self):
        """A real ledger from the seed file, not a contrived example.

        Account 20: one deposit of 115.36, withdrawals of 39.80 and 3.46. Exactly
        72.10 in Decimal, and 72.10000000000001 in float.

        The first version of this test used 1000.10 + 234.20 + 0.30 - 0.04, which
        happens to come out exact in float with that grouping. Float error depends
        on the specific values and the order they are combined, which is the real
        lesson: you cannot tell by looking whether a given sequence will drift.
        """
        deposits = ["115.36"]
        withdrawals = ["39.80", "3.46"]

        exact = sum((Decimal(a) for a in deposits), Decimal("0"))
        for a in withdrawals:
            exact -= Decimal(a)

        drifting = sum(float(a) for a in deposits)
        for a in withdrawals:
            drifting -= float(a)

        self.assertEqual(exact, Decimal("72.10"))
        self.assertNotEqual(drifting, 72.10)
        self.assertEqual(repr(drifting), "72.10000000000001")

    def test_bad_amounts_are_rejected(self):
        for bad in ["-5.00", "0", "0.00", "10.555", "abc", "", "1e5", "5,00", " ", "-0.01"]:
            with self.subTest(amount=bad):
                with self.assertRaises(InvalidAmount):
                    parse_amount(bad)

    def test_good_amounts_are_accepted(self):
        self.assertEqual(parse_amount("0.01"), Decimal("0.01"))
        self.assertEqual(parse_amount("1234.56"), Decimal("1234.56"))
        self.assertEqual(parse_amount(Decimal("99.90")), Decimal("99.90"))

    def test_display_formatting(self):
        self.assertEqual(format_money(Decimal("84210.75")), "84,210.75")
        self.assertEqual(format_money(Decimal("0.01")), "0.01")


# -------------------------------------------------------------- business rules

class TestDeposit(BankTestCase):
    def test_deposit_increases_balance_and_writes_one_entry(self):
        before = len(self.store.transactions_for_account(self.a_checking.account_id))
        self.svc.deposit(self.a_checking.account_id, "100.00", self.aaron)
        self.assertEqual(self.a_checking.balance, Decimal("112.50"))
        after = len(self.store.transactions_for_account(self.a_checking.account_id))
        self.assertEqual(after - before, 1)

    def test_deposit_must_be_positive(self):
        with self.assertRaises(InvalidAmount):
            self.svc.deposit(self.a_checking.account_id, "-10.00", self.aaron)
        self.assertEqual(self.a_checking.balance, Decimal("12.50"))

    def test_precision_survives_a_sequence_of_deposits(self):
        acct = self.svc.open_account(self.aaron, "CHECKING")
        for amount in ["1000.10", "234.20", "0.30"]:
            self.svc.deposit(acct.account_id, amount, self.aaron)
        self.svc.withdraw(acct.account_id, "0.04", self.aaron)
        self.assertEqual(acct.balance, Decimal("1234.56"))


class TestWithdraw(BankTestCase):
    def test_cannot_withdraw_more_than_balance(self):
        with self.assertRaises(InsufficientFunds):
            self.svc.withdraw(self.a_checking.account_id, "12.51", self.aaron)
        self.assertEqual(self.a_checking.balance, Decimal("12.50"))

    def test_withdrawing_the_exact_balance_succeeds(self):
        self.svc.withdraw(self.a_checking.account_id, "12.50", self.aaron)
        self.assertEqual(self.a_checking.balance, Decimal("0.00"))

    def test_a_failed_withdrawal_writes_no_ledger_entry(self):
        before = len(self.store.transactions_for_account(self.a_checking.account_id))
        with self.assertRaises(InsufficientFunds):
            self.svc.withdraw(self.a_checking.account_id, "999.00", self.aaron)
        after = len(self.store.transactions_for_account(self.a_checking.account_id))
        self.assertEqual(before, after)

    def test_savings_minimum_balance_is_enforced_polymorphically(self):
        """500.00 in savings, 25.00 minimum, so 475.00 is available and 475.01 is not.
        The service layer never checks the account type to work this out."""
        self.assertEqual(self.a_savings.available_for_withdrawal(), Decimal("475.00"))
        with self.assertRaises(InsufficientFunds):
            self.svc.withdraw(self.a_savings.account_id, "475.01", self.aaron)
        self.svc.withdraw(self.a_savings.account_id, "475.00", self.aaron)
        self.assertEqual(self.a_savings.balance, SavingsAccount.MINIMUM)

    def test_checking_has_no_minimum(self):
        self.assertEqual(self.a_checking.available_for_withdrawal(), Decimal("12.50"))


class TestFrozenAccounts(BankTestCase):
    def test_frozen_account_rejects_customer_movement(self):
        self.svc.set_frozen(self.e_checking.account_id, True,
                            "Suspected card compromise reported 2026-09-15", self.david)
        with self.assertRaises(AccountNotActive):
            self.svc.deposit(self.e_checking.account_id, "10.00", self.erik)
        with self.assertRaises(AccountNotActive):
            self.svc.withdraw(self.e_checking.account_id, "10.00", self.erik)

    def test_unfreezing_restores_movement(self):
        acct_id = self.e_checking.account_id
        self.svc.set_frozen(acct_id, True, "Suspected card compromise, pending review", self.david)
        self.svc.set_frozen(acct_id, False, "Review complete, no fraud found", self.david)
        self.svc.deposit(acct_id, "10.00", self.erik)
        self.assertEqual(self.e_checking.balance, Decimal("84220.75"))


class TestIdempotency(BankTestCase):
    def test_the_same_submission_is_not_applied_twice(self):
        body = ("100.00", self.aaron, "submit-attempt-0001")
        self.svc.deposit(self.a_checking.account_id, *body)
        with self.assertRaises(DuplicateTransaction):
            self.svc.deposit(self.a_checking.account_id, *body)
        self.assertEqual(self.a_checking.balance, Decimal("112.50"))

    def test_different_ids_both_apply(self):
        self.svc.deposit(self.a_checking.account_id, "10.00", self.aaron, "a")
        self.svc.deposit(self.a_checking.account_id, "10.00", self.aaron, "b")
        self.assertEqual(self.a_checking.balance, Decimal("32.50"))


# --------------------------------------------------------------- authorization

class TestOwnership(BankTestCase):
    def test_a_user_cannot_read_another_users_account(self):
        """The vulnerability in the brief as written."""
        with self.assertRaises(AccountNotFound):
            self.svc.get_account_for(self.e_checking.account_id, self.aaron)

    def test_the_error_does_not_reveal_that_the_account_exists(self):
        """Same exception type and message for 'not yours' and 'does not exist'."""
        try:
            self.svc.get_account_for(self.e_checking.account_id, self.aaron)
        except AccountNotFound as exc:
            not_mine = str(exc)
        try:
            self.svc.get_account_for(99999, self.aaron)
        except AccountNotFound as exc:
            missing = str(exc)
        self.assertEqual(
            not_mine.replace(str(self.e_checking.account_id), "X"),
            missing.replace("99999", "X"),
        )

    def test_a_user_cannot_move_another_users_money(self):
        with self.assertRaises(AccountNotFound):
            self.svc.withdraw(self.e_checking.account_id, "1.00", self.aaron)
        with self.assertRaises(AccountNotFound):
            self.svc.deposit(self.e_checking.account_id, "1.00", self.aaron)
        self.assertEqual(self.e_checking.balance, Decimal("84210.75"))

    def test_a_user_cannot_read_another_users_history(self):
        with self.assertRaises(AccountNotFound):
            self.svc.history(self.e_checking.account_id, self.aaron)

    def test_admin_may_read_any_account(self):
        acct = self.svc.get_account_for(self.e_checking.account_id, self.david)
        self.assertEqual(acct.balance, Decimal("84210.75"))


class TestAdmin(BankTestCase):
    def test_customers_are_locked_out_of_admin_actions(self):
        for call in (
            lambda: self.svc.all_users(self.aaron),
            lambda: self.svc.all_accounts(self.aaron),
            lambda: self.svc.set_frozen(self.a_checking.account_id, True,
                                        "trying to freeze my own account", self.aaron),
            lambda: self.svc.adjust(self.a_checking.account_id, "1000.00", "CREDIT",
                                    "giving myself a thousand dollars", self.aaron),
        ):
            with self.subTest(call=call):
                with self.assertRaises(NotAuthorized):
                    call()

    def test_adjustment_writes_a_ledger_entry_and_an_audit_row(self):
        self.svc.adjust(self.a_checking.account_id, "50.00", "CREDIT",
                        "Reversing a fee misposted on 2026-09-10", self.david)
        self.assertEqual(self.a_checking.balance, Decimal("62.50"))
        self.assertEqual(len(self.svc.audit), 1)
        actor, action, account_id, reason = self.svc.audit[0]
        self.assertEqual(actor, self.david.user_id)
        self.assertEqual(action, "ADJUST_CREDIT")
        self.assertIn("misposted", reason)

    def test_adjustment_requires_a_written_reason(self):
        with self.assertRaises(ValueError):
            self.svc.adjust(self.a_checking.account_id, "50.00", "CREDIT", "oops", self.david)

    def test_adjustment_cannot_take_a_balance_negative(self):
        with self.assertRaises(InsufficientFunds):
            self.svc.adjust(self.a_checking.account_id, "500.00", "DEBIT",
                            "Attempting to claw back more than is present", self.david)
        self.assertEqual(self.a_checking.balance, Decimal("12.50"))

    def test_there_is_no_way_for_an_admin_to_set_a_balance_directly(self):
        """If someone adds a set_balance method, this test should fail and the
        review conversation should happen."""
        self.assertFalse(hasattr(self.svc, "set_balance"))
        self.assertFalse(hasattr(self.a_checking, "set_balance"))

    def test_balance_has_no_public_setter(self):
        with self.assertRaises(AttributeError):
            self.a_checking.balance = Decimal("1000000.00")


# -------------------------------------------------------------------- transfer

class TestTransfer(BankTestCase):
    def test_transfer_moves_money_and_writes_both_legs(self):
        self.svc.transfer(self.a_savings.account_id, self.e_checking.account_id,
                          "100.00", self.aaron)
        self.assertEqual(self.a_savings.balance, Decimal("400.00"))
        self.assertEqual(self.e_checking.balance, Decimal("84310.75"))

    def test_cannot_transfer_from_an_account_you_do_not_own(self):
        with self.assertRaises(AccountNotFound):
            self.svc.transfer(self.e_checking.account_id, self.a_checking.account_id,
                              "100.00", self.aaron)

    def test_a_failed_transfer_moves_nothing(self):
        with self.assertRaises(InsufficientFunds):
            self.svc.transfer(self.a_checking.account_id, self.e_checking.account_id,
                              "9999.00", self.aaron)
        self.assertEqual(self.a_checking.balance, Decimal("12.50"))
        self.assertEqual(self.e_checking.balance, Decimal("84210.75"))


# ------------------------------------------------------------------ invariants

class TestInvariants(BankTestCase):
    def test_opening_balance_gets_a_ledger_entry(self):
        """An account given a balance with no entry behind it breaks reconciliation
        from the moment it exists."""
        stored, ledger = self.svc.reconcile(self.a_checking.account_id)
        self.assertEqual(stored, ledger)
        self.assertEqual(stored, Decimal("12.50"))

    def test_reconciliation_holds_across_a_long_sequence(self):
        acct = self.a_savings.account_id
        for amount in ["10.01", "99.99", "0.01", "1234.56"]:
            self.svc.deposit(acct, amount, self.aaron)
        for amount in ["5.55", "0.01", "100.00"]:
            self.svc.withdraw(acct, amount, self.aaron)
        stored, ledger = self.svc.reconcile(acct)
        self.assertEqual(stored, ledger)

    def test_history_is_paginated(self):
        acct = self.a_savings.account_id
        for _ in range(25):
            self.svc.deposit(acct, "1.00", self.aaron)
        rows, total = self.svc.history(acct, self.aaron, page=1, page_size=10)
        self.assertEqual(len(rows), 10)
        self.assertEqual(total, 26)  # 25 deposits plus the opening entry
        rows, _ = self.svc.history(acct, self.aaron, page=3, page_size=10)
        self.assertEqual(len(rows), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
