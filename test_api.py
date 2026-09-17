"""Tests for the controller layer. Standard library only.

    MONGO_TESTS=1 python -m unittest -v

`test_bank.py` proves the RULES are right. This file proves the HTTP layer maps
them correctly - that a domain exception becomes the right status code, that a
token is actually required, and that the ownership check the service performs is
not bypassed by any route.

Almost every test here calls `api.handle(...)` directly rather than opening a
socket. `BankAPI.handle` takes plain arguments and returns a plain
`(status, dict)`, so the routing, the auth and the error mapping are all testable
without a server, and the suite stays fast enough to run on every save. The one
exception is `TestLiveServer` at the bottom, which boots a real server on a real
port so that the socket plumbing is covered too.

A note on the fixture: it does NOT load the seed roster, because hashing the demo
password costs about 0.6 seconds and these tests do not need 20 accounts. The
seed gets one test class of its own.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from bank import BankAPI, BankService, BankStore
from bank import seed as seed_module
from bank.api import make_handler_class
from bank.models import SavingsAccount
from bank.security import hash_password, new_token, verify_password

PASSWORD = "CorrectHorse1!"

# PBKDF2 at the production 600,000 rounds costs about 0.6 seconds per call, which
# is the entire point of the setting and completely wrong for a test suite - at
# the default this file takes 12 seconds, and a suite slow enough to skip is a
# suite that gets skipped. So fixtures hash at 1,000 rounds.
#
# The round count is stored inside each hash, so `verify_password` still works
# unchanged; only the cost differs. `TestPasswordHashing.test_the_default_cost_
# is_high` is the test that guards the real default, so lowering it here cannot
# hide a weakened production setting.
FAST_ROUNDS = 1_000

# One password, hashed once for the whole module. See seed.py for why.
SHARED_HASH = hash_password(PASSWORD, rounds=FAST_ROUNDS)


class ApiTestCase(unittest.TestCase):
    """Two customers, one admin, three accounts, and a helper per verb."""

    def setUp(self):
        self.store = BankStore()
        self.svc = BankService(self.store)
        self.api = BankAPI(self.svc)

        self.aaron = self.svc.register_user("Aaron Forrester", "aaron@example.com",
                                            password_hash=SHARED_HASH)
        self.erik = self.svc.register_user("Erik Mayes", "erik@example.com",
                                           password_hash=SHARED_HASH)
        self.david = self.svc.register_user("David Gusmao", "david@example.com",
                                            role="ADMIN", password_hash=SHARED_HASH)

        self.a_checking = self.svc.open_account(self.aaron, "CHECKING", 10000)
        self.a_savings = self.svc.open_account(self.aaron, "SAVINGS", 50000)
        self.e_checking = self.svc.open_account(self.erik, "CHECKING", 8421075)
        self._tokens: dict[int, str] = {}   # see token_for

    def tearDown(self):
        """Same invariant as test_bank.py, asserted after every HTTP call too: no
        route may change a balance without writing a matching ledger entry."""
        self.assertEqual(self.svc.reconcile_all(), [],
                         "balance and ledger disagree after this test")

    # -- helpers ---------------------------------------------------------

    def token_for(self, user) -> str:
        """A real session, through the service, not a hand-built string. Tokens
        are stored rows now, so one that skipped `issue_token` would not exist as
        far as `_authenticate` is concerned.

        Cached per user, so a test making six calls holds one session rather than
        six. A test that cares about issuing more than one calls the service.
        """
        if user.user_id not in self._tokens:
            self._tokens[user.user_id] = self.svc.issue_token(user).token
        return self._tokens[user.user_id]

    def auth(self, user) -> dict:
        return {"authorization": f"Bearer {self.token_for(user)}"}

    def get(self, path, user=None):
        return self.api.handle("GET", path, b"", self.auth(user) if user else {})

    def post(self, path, body=None, user=None):
        raw = json.dumps(body or {}).encode("utf-8")
        return self.api.handle("POST", path, raw, self.auth(user) if user else {})


# ======================================================================= auth

class TestAuthentication(ApiTestCase):
    def test_health_needs_no_token(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_protected_route_without_a_token_is_401(self):
        status, body = self.get("/api/accounts")
        self.assertEqual(status, 401)
        self.assertIn("token", body["error"])

    def test_a_garbage_token_is_401(self):
        status, _ = self.api.handle("GET", "/api/accounts", b"",
                                    {"authorization": "Bearer not-a-real-token"})
        self.assertEqual(status, 401)

    def test_a_token_that_was_never_issued_is_rejected(self):
        """A correctly shaped token that is not in the tokens table is nobody's.

        This is what replaced the signature check. The token carries no claims to
        forge, so the only way to hold one is to be given it: a well-formed guess
        fails for the same reason "not-a-real-token" does, which is that the
        lookup comes back empty.
        """
        status, _ = self.api.handle("GET", "/api/admin/users", b"",
                                    {"authorization": f"Bearer {new_token()}"})
        self.assertEqual(status, 401)

    def test_an_expired_token_is_rejected(self):
        expired = self.svc.issue_token(self.aaron, ttl=-1).token
        # The row is still there; what fails is the expiry check, not the lookup.
        self.assertIsNotNone(self.store.find_token(expired))
        status, _ = self.api.handle("GET", "/api/accounts", b"",
                                    {"authorization": f"Bearer {expired}"})
        self.assertEqual(status, 401)

    def test_a_token_is_bound_to_the_user_it_was_issued_for(self):
        """Erik's session reads Erik's profile and cannot become Aaron's."""
        status, me = self.api.handle("GET", "/api/auth/me", b"",
                                     {"authorization": f"Bearer {self.token_for(self.erik)}"})
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["email"], "erik@example.com")

    def test_login_returns_a_working_token(self):
        status, body = self.post("/api/auth/login",
                                 {"email": "aaron@example.com", "password": PASSWORD})
        self.assertEqual(status, 200)
        status, me = self.api.handle("GET", "/api/auth/me", b"",
                                     {"authorization": f"Bearer {body['token']}"})
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["email"], "aaron@example.com")

    def test_login_saves_the_token_against_the_user(self):
        """The token the client is handed is a row in the tokens table, and that
        row names the user it belongs to and when it stops working."""
        _, body = self.post("/api/auth/login",
                            {"email": "aaron@example.com", "password": PASSWORD})
        session = self.store.find_token(body["token"])
        self.assertIsNotNone(session)
        self.assertEqual(session.user_id, self.aaron.user_id)
        self.assertFalse(session.is_expired())
        self.assertGreater(body["expiresIn"], 0)

    def test_register_saves_a_token_too(self):
        status, body = self.post("/api/auth/register", {
            "name": "New Person", "email": "new@example.com", "password": PASSWORD,
        })
        self.assertEqual(status, 201)
        session = self.store.find_token(body["token"])
        self.assertIsNotNone(session)
        self.assertEqual(session.user_id, body["user"]["userId"])

    def test_one_user_may_hold_several_tokens_at_once(self):
        """A phone and a laptop are two sessions. Logging in on the second must
        not invalidate the first, which is why user_id is not unique in the
        tokens table."""
        first = self.token_for(self.aaron)
        _, body = self.post("/api/auth/login",
                            {"email": "aaron@example.com", "password": PASSWORD})
        second = body["token"]
        self.assertNotEqual(first, second)
        for token in (first, second):
            status, _ = self.api.handle("GET", "/api/accounts", b"",
                                        {"authorization": f"Bearer {token}"})
            self.assertEqual(status, 200)

    def test_two_tokens_are_never_the_same_string(self):
        """The token is the primary key, so a repeat would collide with a live
        session. 200 samples is not a proof of randomness - it is a guard against
        the token accidentally becoming derived from the user or the second."""
        issued = {self.svc.issue_token(self.aaron).token for _ in range(200)}
        self.assertEqual(len(issued), 200)

    def test_a_failed_login_is_401_not_403(self):
        """401 means 'authenticate'. 403 means 'authenticating again will not help'."""
        status, _ = self.post("/api/auth/login",
                              {"email": "aaron@example.com", "password": "wrong-one"})
        self.assertEqual(status, 401)

    def test_login_does_not_reveal_whether_an_email_is_registered(self):
        """Identical status and message for a wrong password and an unknown user.

        A different reply turns the login form into a tool for discovering which
        addresses have accounts.
        """
        _, wrong_password = self.post("/api/auth/login",
                                      {"email": "aaron@example.com", "password": "nope1234"})
        _, unknown_email = self.post("/api/auth/login",
                                     {"email": "nobody@example.com", "password": "nope1234"})
        self.assertEqual(wrong_password, unknown_email)

    def test_a_password_hash_never_appears_in_a_response(self):
        status, body = self.post("/api/auth/register", {
            "name": "New Person", "email": "new@example.com", "password": PASSWORD,
        })
        self.assertEqual(status, 201)
        self.assertNotIn("passwordHash", body["user"])
        self.assertNotIn("password_hash", json.dumps(body))
        self.assertNotIn(PASSWORD, json.dumps(body))

    def test_registration_cannot_make_you_an_admin(self):
        """The most common privilege-escalation bug in this exact endpoint: the
        handler reads `role` from the body because the model has the field."""
        status, body = self.post("/api/auth/register", {
            "name": "Sneaky", "email": "sneaky@example.com",
            "password": PASSWORD, "role": "ADMIN",
        })
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["role"], "CUSTOMER")

    def test_registering_a_duplicate_email_is_409(self):
        status, _ = self.post("/api/auth/register", {
            "name": "Impostor", "email": "AARON@example.com", "password": PASSWORD,
        })
        self.assertEqual(status, 409)


class TestAdminRegistration(ApiTestCase):
    """Registering as an admin: only with the code, and only if one is set."""

    ADMIN_CODE = "Group2Rules!"

    def open_api(self):
        """A second API over the same service, with admin registration open."""
        return BankAPI(self.svc, admin_code=self.ADMIN_CODE)

    @staticmethod
    def register(api, email, code=None):
        body = {"name": "New Person", "email": email, "password": PASSWORD}
        if code is not None:
            body["adminCode"] = code
        return api.handle("POST", "/api/auth/register",
                          json.dumps(body).encode("utf-8"), {})

    def test_no_code_still_makes_a_customer(self):
        status, body = self.register(self.open_api(), "plain@example.com")
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["role"], "CUSTOMER")

    def test_the_right_code_makes_an_admin(self):
        status, body = self.register(self.open_api(), "boss@example.com",
                                     self.ADMIN_CODE)
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["role"], "ADMIN")

    def test_the_wrong_code_is_refused_and_creates_nobody(self):
        status, body = self.register(self.open_api(), "sneaky@example.com", "wrong")
        self.assertEqual(status, 403)
        self.assertIn("admin code", body["error"])
        # The refusal has to happen before the user is created, or a failed
        # attempt would leave a customer behind and burn the email address.
        self.assertIsNone(self.store.find_user_by_email("sneaky@example.com"))

    def test_no_code_configured_means_no_admin_can_register(self):
        """`self.api` is built without an admin_code, which is the default. A
        deployment nobody configured must not be able to grow admins."""
        status, body = self.register(self.api, "boss@example.com", self.ADMIN_CODE)
        self.assertEqual(status, 403)
        self.assertIsNone(self.store.find_user_by_email("boss@example.com"))

    def test_a_non_string_code_is_refused_not_crashed(self):
        """compare_digest raises TypeError on a non-string, which would be a 500
        for what is really a bad request."""
        for junk in (True, 12345, ["Group2Rules!"], {"code": "Group2Rules!"}):
            with self.subTest(junk=junk):
                status, _ = self.open_api().handle(
                    "POST", "/api/auth/register",
                    json.dumps({"name": "X", "email": f"x{id(junk)}@example.com",
                                "password": PASSWORD, "adminCode": junk}).encode(),
                    {})
                self.assertEqual(status, 403)

    def test_the_new_admin_can_actually_reach_an_admin_route(self):
        """The role has to be real, not just a string in the response."""
        api = self.open_api()
        _, body = self.register(api, "boss@example.com", self.ADMIN_CODE)
        headers = {"authorization": f"Bearer {body['token']}"}
        status, _ = api.handle("GET", "/api/admin/users", b"", headers)
        self.assertEqual(status, 200)


class TestProfileEditing(ApiTestCase):
    """POST /api/auth/me - editing your own name and email, and nobody else's."""

    def test_needs_a_token(self):
        status, _ = self.post("/api/auth/me", {"name": "Nobody"})
        self.assertEqual(status, 401)

    def test_changes_the_name(self):
        status, body = self.post("/api/auth/me", {"name": "Aaron F."}, self.aaron)
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["name"], "Aaron F.")
        self.assertEqual(self.store.get_user(self.aaron.user_id).name, "Aaron F.")

    def test_changes_the_email_and_the_new_one_can_log_in(self):
        status, _ = self.post("/api/auth/me", {"email": "aaron.f@example.com"},
                              self.aaron)
        self.assertEqual(status, 200)
        # The email is the login identifier, so a rename that did not move the
        # index would lock the user out of the account they just edited.
        found = self.store.find_user_by_email("aaron.f@example.com")
        self.assertEqual(found.user_id, self.aaron.user_id)
        self.assertIsNone(self.store.find_user_by_email("aaron@example.com"))

    def test_an_omitted_field_is_left_alone(self):
        _, body = self.post("/api/auth/me", {"name": "Just The Name"}, self.aaron)
        self.assertEqual(body["user"]["email"], "aaron@example.com")

    def test_a_blank_field_is_refused_rather_than_erasing(self):
        for field in ("name", "email"):
            with self.subTest(field=field):
                status, _ = self.post("/api/auth/me", {field: "   "}, self.aaron)
                self.assertEqual(status, 400)

    def test_an_empty_body_is_refused(self):
        status, body = self.post("/api/auth/me", {}, self.aaron)
        self.assertEqual(status, 400)
        self.assertIn("name", body["error"])

    def test_taking_somebody_elses_email_is_a_conflict(self):
        status, _ = self.post("/api/auth/me", {"email": "erik@example.com"},
                              self.aaron)
        self.assertEqual(status, 409)
        self.assertEqual(self.store.get_user(self.aaron.user_id).email,
                         "aaron@example.com")

    def test_keeping_your_own_email_is_not_a_conflict(self):
        """Submitting the form unchanged must not collide with yourself."""
        status, _ = self.post("/api/auth/me", {"email": "aaron@example.com"},
                              self.aaron)
        self.assertEqual(status, 200)

    def test_the_body_cannot_name_another_user(self):
        """The user edited comes from the token. A userId in the body is ignored,
        not honoured - this is the same hole /api/accounts closes."""
        status, body = self.post("/api/auth/me",
                                 {"userId": self.erik.user_id, "name": "Hijacked"},
                                 self.aaron)
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["userId"], self.aaron.user_id)
        self.assertEqual(self.store.get_user(self.erik.user_id).name, "Erik Mayes")

    def test_role_cannot_be_changed_through_the_profile(self):
        status, body = self.post("/api/auth/me",
                                 {"name": "Aaron", "role": "ADMIN"}, self.aaron)
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["role"], "CUSTOMER")
        # And the token still will not open an admin route.
        self.assertEqual(self.get("/api/admin/users", self.aaron)[0], 403)


class TestPasswordHashing(unittest.TestCase):
    """Direct tests of security.py, which nothing else exercises in isolation."""

    def test_a_hash_verifies_only_the_right_password(self):
        encoded = hash_password("s3cret-password", rounds=FAST_ROUNDS)
        self.assertTrue(verify_password("s3cret-password", encoded))
        self.assertFalse(verify_password("s3cret-passwore", encoded))
        self.assertFalse(verify_password("", encoded))

    def test_the_same_password_hashes_differently_every_time(self):
        """Per-user salt. Without it, one cracked hash unlocks every account that
        shares that password, and equal hashes reveal who shares one."""
        self.assertNotEqual(hash_password("same-password-twice", rounds=FAST_ROUNDS),
                            hash_password("same-password-twice", rounds=FAST_ROUNDS))

    def test_the_plaintext_is_not_in_the_stored_value(self):
        self.assertNotIn("s3cret", hash_password("s3cret-password", rounds=FAST_ROUNDS))

    def test_the_default_cost_is_high(self):
        """The guard on FAST_ROUNDS. Fixtures hash cheaply so the suite stays
        fast; if that ever leaks into the real default, this fails.

        A hash also carries its own round count, so old hashes keep verifying
        after the default is raised. That is what makes raising it safe."""
        from bank.security import PBKDF2_ROUNDS
        self.assertGreaterEqual(PBKDF2_ROUNDS, 600_000)
        cheap = hash_password("cost-is-recorded-in-the-hash", rounds=FAST_ROUNDS)
        self.assertEqual(cheap.split("$")[1], str(FAST_ROUNDS))

    def test_verify_never_raises_on_malformed_input(self):
        for stored in (None, "", "not-a-hash", "pbkdf2_sha256$x$y$z", "a$b$c$d"):
            with self.subTest(stored=stored):
                self.assertFalse(verify_password("anything", stored))

    def test_a_short_password_is_refused(self):
        with self.assertRaises(ValueError):
            hash_password("short")

class TestAdminRoutes(ApiTestCase):
    def test_every_admin_route_refuses_a_customer_with_403(self):
        cases = [
            ("GET", "/api/admin/users", None),
            ("GET", "/api/admin/accounts", None),
            ("GET", "/api/admin/audit", None),
            ("GET", "/api/admin/reconciliation", None),
            ("POST", f"/api/admin/accounts/{self.a_checking.account_id}/freeze",
             {"frozen": True, "reason": "freezing my own account for fun"}),
            ("POST", f"/api/admin/accounts/{self.a_checking.account_id}/adjust",
             {"amount": 999900, "direction": "CREDIT",
              "reason": "giving myself nine thousand dollars"}),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                status, _ = (self.get(path, self.aaron) if method == "GET"
                             else self.post(path, body, self.aaron))
                self.assertEqual(status, 403)

    def test_admin_adjustment_writes_a_ledger_entry_and_an_audit_row(self):
        status, body = self.post(
            f"/api/admin/accounts/{self.a_checking.account_id}/adjust",
            {"amount": 5000, "direction": "CREDIT",
             "reason": "Reversing a fee misposted on 2026-09-10"}, self.david)
        self.assertEqual(status, 201)
        self.assertEqual(body["account"]["balance"], 15000)

        status, audit = self.get("/api/admin/audit", self.david)
        self.assertEqual(audit["entries"][-1]["action"], "ADJUST_CREDIT")
        self.assertEqual(audit["entries"][-1]["actorUserId"], self.david.user_id)

    def test_an_adjustment_without_a_real_reason_is_400(self):
        status, _ = self.post(
            f"/api/admin/accounts/{self.a_checking.account_id}/adjust",
            {"amount": 5000, "direction": "CREDIT", "reason": "oops"}, self.david)
        self.assertEqual(status, 400)

    def test_there_is_no_route_that_sets_a_balance(self):
        """If someone adds one, this fails and the review conversation happens."""
        paths = [route.pattern.pattern for route in self.api.routes]
        self.assertFalse([p for p in paths if "balance" in p.lower()])

    def test_reconciliation_endpoint_reports_balanced(self):
        status, body = self.get("/api/admin/reconciliation", self.david)
        self.assertEqual(status, 200)
        self.assertTrue(body["balanced"])
        self.assertEqual(body["discrepancies"], [])

    def test_freeze_then_unfreeze(self):
        acct = self.e_checking.account_id
        status, body = self.post(f"/api/admin/accounts/{acct}/freeze",
                                 {"frozen": True, "reason": "Suspected card compromise"},
                                 self.david)
        self.assertEqual(status, 200)
        self.assertEqual(body["account"]["status"], "FROZEN")

        status, _ = self.post(f"/api/accounts/{acct}/deposit",
                              {"amount": 1000}, self.erik)
        self.assertEqual(status, 409, "a frozen account must refuse a deposit")

        self.post(f"/api/admin/accounts/{acct}/freeze",
                  {"frozen": False, "reason": "Review complete, no fraud found"},
                  self.david)
        status, _ = self.post(f"/api/accounts/{acct}/deposit",
                              {"amount": 1000}, self.erik)
        self.assertEqual(status, 201)

# ============================================================== authorization

class TestUserSearch(ApiTestCase):
    """GET /api/users/search - finding somebody to pay."""

    def search(self, q, user=None):
        return self.get(f"/api/users/search?q={q}", user or self.aaron)

    def test_needs_a_token(self):
        status, _ = self.api.handle("GET", "/api/users/search?q=erik", b"", {})
        self.assertEqual(status, 401)

    def test_finds_by_name_case_insensitively(self):
        for q in ("erik", "ERIK", "Erik", "mayes"):
            with self.subTest(q=q):
                status, body = self.search(q)
                self.assertEqual(status, 200)
                self.assertEqual([u["email"] for u in body["users"]],
                                 ["erik@example.com"])

    def test_finds_by_email(self):
        _, body = self.search("erik@exam")
        self.assertEqual([u["name"] for u in body["users"]], ["Erik Mayes"])

    def test_leaves_the_caller_out_of_their_own_results(self):
        """Transferring to yourself is refused anyway; offering it invites it."""
        _, body = self.search("aaron")
        self.assertEqual(body["users"], [])

    def test_one_character_returns_nothing(self):
        """A single letter matches most of a roster, which is a directory dump
        rather than a search."""
        _, body = self.search("a")
        self.assertEqual(body["users"], [])

    def test_no_password_field_ever_comes_back(self):
        _, body = self.search("erik")
        self.assertNotIn("password_hash", body["users"][0])
        self.assertNotIn("passwordHash", body["users"][0])


class TestTransferToAPerson(ApiTestCase):
    """POST /api/transfers with toUserId instead of toAccountId."""

    def test_lands_in_that_persons_primary_account(self):
        status, body = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "toUserId": self.erik.user_id,
            "amount": 5000,
        }, self.aaron)
        self.assertEqual(status, 201)
        self.assertEqual(body["credit"]["accountId"], self.e_checking.account_id)

    def test_sending_both_destinations_is_refused(self):
        """A mismatched pair would move money somewhere the caller did not name."""
        status, body = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "toAccountId": self.e_checking.account_id,
            "toUserId": self.erik.user_id,
            "amount": 5000,
        }, self.aaron)
        self.assertEqual(status, 400)
        self.assertIn("exactly one", body["error"])

    def test_sending_neither_is_refused(self):
        status, _ = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "amount": 5000,
        }, self.aaron)
        self.assertEqual(status, 400)

    def test_a_user_who_does_not_exist_is_a_404(self):
        status, _ = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "toUserId": 9999,
            "amount": 5000,
        }, self.aaron)
        self.assertEqual(status, 404)

    def test_a_user_with_no_account_is_a_404(self):
        loner = self.svc.register_user("No Accounts", "loner@example.com",
                                       password_hash=SHARED_HASH)
        status, body = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "toUserId": loner.user_id,
            "amount": 5000,
        }, self.aaron)
        self.assertEqual(status, 404)
        self.assertIn("no account", body["error"])

    def test_the_same_person_always_resolves_to_the_same_account(self):
        """A payee whose destination moved between transfers would be alarming."""
        self.svc.open_account(self.erik, "SAVINGS", 100)
        first = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "toUserId": self.erik.user_id, "amount": 100}, self.aaron)[1]
        second = self.post("/api/transfers", {
            "fromAccountId": self.a_checking.account_id,
            "toUserId": self.erik.user_id, "amount": 100}, self.aaron)[1]
        self.assertEqual(first["credit"]["accountId"], second["credit"]["accountId"])


class TestOwnershipOverHttp(ApiTestCase):
    """The IDOR row from the seed document's test table, at the HTTP boundary."""

    def test_reading_another_users_account_is_404(self):
        status, _ = self.get(f"/api/accounts/{self.e_checking.account_id}", self.aaron)
        self.assertEqual(status, 404)

    def test_the_404_is_indistinguishable_from_a_missing_account(self):
        """Not 403. A distinct 'forbidden' confirms the account exists, which is
        the fact the status code is there to withhold."""
        _, not_mine = self.get(f"/api/accounts/{self.e_checking.account_id}", self.aaron)
        _, missing = self.get("/api/accounts/99999", self.aaron)
        self.assertEqual(
            not_mine["error"].replace(str(self.e_checking.account_id), "X"),
            missing["error"].replace("99999", "X"),
        )

    def test_moving_another_users_money_is_404(self):
        for path in ("deposit", "withdraw"):
            with self.subTest(path=path):
                status, _ = self.post(
                    f"/api/accounts/{self.e_checking.account_id}/{path}",
                    {"amount": 1000}, self.aaron)
                self.assertEqual(status, 404)
        # And nothing moved: the 404 is a refusal, not a silent no-op after a write.
        self.assertEqual(self.e_checking.balance, 8421075)

    def test_reading_another_users_history_is_404(self):
        status, _ = self.get(
            f"/api/accounts/{self.e_checking.account_id}/transactions", self.aaron)
        self.assertEqual(status, 404)

    def test_transferring_out_of_an_account_you_do_not_own_is_404(self):
        status, _ = self.post("/api/transfers", {
            "fromAccountId": self.e_checking.account_id,
            "toAccountId": self.a_checking.account_id,
            "amount": 100000,
        }, self.aaron)
        self.assertEqual(status, 404)

    def test_an_admin_may_read_any_account(self):
        status, body = self.get(f"/api/accounts/{self.e_checking.account_id}", self.david)
        self.assertEqual(status, 200)
        self.assertEqual(body["account"]["balance"], 8421075)

    def test_you_cannot_open_an_account_for_someone_else(self):
        status, _ = self.post("/api/accounts", {
            "userId": self.erik.user_id, "accountType": "CHECKING",
        }, self.aaron)
        self.assertEqual(status, 403)

    def test_an_admin_may_open_an_account_for_someone_else(self):
        status, body = self.post("/api/accounts", {
            "userId": self.erik.user_id, "accountType": "SAVINGS",
        }, self.david)
        self.assertEqual(status, 201)
        self.assertEqual(body["account"]["userId"], self.erik.user_id)

    def test_an_admin_may_not_open_an_account_for_themselves(self):
        """The role is supervisory. An admin who also banks here could freeze
        their own account and adjust their own balance, so they do not get one."""
        status, body = self.post("/api/accounts", {"accountType": "CHECKING"},
                                 self.david)
        self.assertEqual(status, 403)
        self.assertIn("admin", body["error"])

    def test_an_admin_may_not_open_an_account_for_themselves_by_id(self):
        """Naming your own id in the body is the same request in a costume."""
        status, _ = self.post("/api/accounts", {
            "userId": self.david.user_id, "accountType": "CHECKING",
        }, self.david)
        self.assertEqual(status, 403)

# ================================================================ money moves

class TestMoneyOverHttp(ApiTestCase):
    def test_deposit_returns_the_new_balance_as_integer_cents(self):
        """Money leaves as a JSON integer of cents - never a fractional number,
        and no longer as a quoted string.

        A fractional literal becomes an IEEE 754 double the moment JSON.parse
        runs, which throws away the precision every other layer preserves. An
        integer does not: JSON integers are exact to 2^53.
        """
        status, body = self.post(f"/api/accounts/{self.a_checking.account_id}/deposit",
                                 {"amount": 2550}, self.aaron)
        self.assertEqual(status, 201)
        self.assertEqual(body["account"]["balance"], 12550)      # 125.50
        self.assertIsInstance(body["account"]["balance"], int)
        self.assertIsInstance(body["transaction"]["amount"], int)

        # And it really is an unquoted integer in the serialized form, not just
        # an int in Python that some later change might start quoting.
        serialized = json.dumps(body, indent=2)
        self.assertIn('"balance": 12550', serialized)
        self.assertNotIn('"12550"', serialized)
        # Nothing anywhere in the payload carries a decimal point.
        self.assertNotIn("125.50", serialized)

    def test_precision_survives_a_sequence_of_http_deposits(self):
        """The account-11 sequence from the seed file, driven through the API."""
        status, body = self.post("/api/accounts", {"accountType": "CHECKING"}, self.aaron)
        acct = body["account"]["accountId"]
        for amount in (100010, 23420, 30):
            self.post(f"/api/accounts/{acct}/deposit", {"amount": amount}, self.aaron)
        _, body = self.post(f"/api/accounts/{acct}/withdraw",
                            {"amount": 4}, self.aaron)
        self.assertEqual(body["account"]["balance"], 123456)
        self.assertNotIn("1234.5599", json.dumps(body))

    def test_overdraft_is_409_and_moves_nothing(self):
        status, _ = self.post(f"/api/accounts/{self.a_checking.account_id}/withdraw",
                              {"amount": 10001}, self.aaron)
        self.assertEqual(status, 409)
        _, body = self.get(f"/api/accounts/{self.a_checking.account_id}", self.aaron)
        self.assertEqual(body["account"]["balance"], 10000)

    def test_savings_minimum_is_enforced_through_the_api(self):
        """The floor a savings account holds is visible in the response and
        enforced on withdrawal, whatever that floor is set to.

        Derived from `SavingsAccount.MINIMUM` rather than hardcoded: the minimum
        is 0 today, so the whole balance is withdrawable, but the shape of the
        rule is what is being tested. No route knows it; the subclass does.
        """
        available = self.a_savings.balance - SavingsAccount.MINIMUM

        _, body = self.get(f"/api/accounts/{self.a_savings.account_id}", self.aaron)
        self.assertEqual(body["account"]["availableForWithdrawal"], available)
        self.assertEqual(body["account"]["minimumBalance"], SavingsAccount.MINIMUM)

        status, _ = self.post(f"/api/accounts/{self.a_savings.account_id}/withdraw",
                              {"amount": available + 1}, self.aaron)
        self.assertEqual(status, 409)

    def test_bad_amounts_are_400_before_anything_moves(self):
        """Zero, negatives, and every shape of non-integer.

        The dollar strings matter most: they are what the previous version of
        this API accepted, so a client that was not updated sends "50.00" and
        has to be refused. Reading it as 50 cents would be a hundredfold error
        in the customer's favour, and "5000.00" a hundredfold the other way.
        """
        bad = [0, -50, -1,                             # not positive
               "50.00", "5000", "abc", "1e5", "", "5,00",  # strings
               10.555, 50.0, 0.01,                     # floats
               True, None, [5000], {"cents": 5000}]    # nonsense
        for amount in bad:
            with self.subTest(amount=amount):
                status, _ = self.post(
                    f"/api/accounts/{self.a_checking.account_id}/deposit",
                    {"amount": amount}, self.aaron)
                self.assertEqual(status, 400)
        # Not one of them moved anything.
        self.assertEqual(self.a_checking.balance, 10000)

    def test_a_fractional_json_number_is_rejected(self):
        """`{"amount": 10.50}` parses to a Python float, which money.py refuses.

        The brief's own sample body uses a fractional number, so this is the case
        that will actually be sent. It is ambiguous as well as imprecise - in an
        API that speaks cents, 10.50 could mean ten and a half cents or ten
        dollars fifty - so 400 with a clear message beats guessing.
        """
        raw = json.dumps({"amount": 10.50}).encode("utf-8")
        status, body = self.api.handle(
            "POST", f"/api/accounts/{self.a_checking.account_id}/deposit",
            raw, self.auth(self.aaron))
        self.assertEqual(status, 400)
        self.assertIn("cents", body["error"].lower())

    def test_a_missing_amount_is_400(self):
        status, body = self.post(f"/api/accounts/{self.a_checking.account_id}/deposit",
                                 {}, self.aaron)
        self.assertEqual(status, 400)
        self.assertIn("amount", body["error"])

    def test_the_same_client_txn_id_twice_is_409(self):
        """The double-clicked submit button."""
        body = {"amount": 4000, "clientTxnId": "submit-attempt-0001"}
        status, first = self.post(f"/api/accounts/{self.a_checking.account_id}/deposit",
                                  body, self.aaron)
        self.assertEqual(status, 201)
        self.assertEqual(first["account"]["balance"], 14000)

        status, _ = self.post(f"/api/accounts/{self.a_checking.account_id}/deposit",
                              body, self.aaron)
        self.assertEqual(status, 409)

        _, after = self.get(f"/api/accounts/{self.a_checking.account_id}", self.aaron)
        self.assertEqual(after["account"]["balance"], 14000)

    def test_transfer_moves_both_legs(self):
        status, body = self.post("/api/transfers", {
            "fromAccountId": self.a_savings.account_id,
            "toAccountId": self.e_checking.account_id,
            "amount": 10000,
        }, self.aaron)
        self.assertEqual(status, 201)
        self.assertEqual(body["debit"]["type"], "TRANSFER_OUT")
        self.assertEqual(body["credit"]["type"], "TRANSFER_IN")
        self.assertEqual(body["account"]["balance"], 40000)


class TestHistoryAndPagination(ApiTestCase):
    def test_history_comes_back_in_an_envelope(self):
        status, body = self.get(
            f"/api/accounts/{self.a_checking.account_id}/transactions", self.aaron)
        self.assertEqual(status, 200)
        for key in ("items", "page", "pageSize", "total", "totalPages"):
            self.assertIn(key, body)

    def test_paging_is_honoured(self):
        acct = self.a_checking.account_id
        for _ in range(25):
            self.post(f"/api/accounts/{acct}/deposit", {"amount": 100}, self.aaron)
        _, page1 = self.get(f"/api/accounts/{acct}/transactions?page=1&pageSize=10",
                            self.aaron)
        self.assertEqual(len(page1["items"]), 10)
        self.assertEqual(page1["total"], 26)   # 25 deposits plus the opening entry
        self.assertEqual(page1["totalPages"], 3)
        _, page3 = self.get(f"/api/accounts/{acct}/transactions?page=3&pageSize=10",
                            self.aaron)
        self.assertEqual(len(page3["items"]), 6)

    def test_page_size_is_clamped_and_the_response_says_so(self):
        """Ask for 5000 rows and the service caps it at 100. The echoed pageSize
        must be what was used, or the client's paging arithmetic disagrees."""
        _, body = self.get(
            f"/api/accounts/{self.a_checking.account_id}/transactions?pageSize=5000",
            self.aaron)
        self.assertEqual(body["pageSize"], 100)

    def test_a_nonsense_page_number_does_not_500(self):
        status, body = self.get(
            f"/api/accounts/{self.a_checking.account_id}/transactions?page=abc",
            self.aaron)
        self.assertEqual(status, 200)
        self.assertEqual(body["page"], 1)

    def test_filtering_by_type(self):
        acct = self.a_checking.account_id
        self.post(f"/api/accounts/{acct}/withdraw", {"amount": 1000}, self.aaron)
        _, body = self.get(f"/api/accounts/{acct}/transactions?type=WITHDRAWAL",
                           self.aaron)
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["type"], "WITHDRAWAL")
        self.assertEqual(body["items"][0]["direction"], "DEBIT")


# =================================================================== routing

class TestRouting(ApiTestCase):
    def test_an_unknown_path_is_404(self):
        status, _ = self.get("/api/nope", self.aaron)
        self.assertEqual(status, 404)

    def test_the_wrong_method_on_a_real_path_is_405_not_404(self):
        """A POST to a GET-only URL is a different mistake from a URL that does
        not exist, and saying so saves the caller hunting for a typo."""
        status, _ = self.post("/api/health", {}, self.aaron)
        self.assertEqual(status, 405)

    def test_a_non_numeric_account_id_is_404_not_a_crash(self):
        status, _ = self.get("/api/accounts/not-a-number", self.aaron)
        self.assertEqual(status, 404)

    def test_a_body_that_is_not_json_is_400(self):
        status, body = self.api.handle("POST", "/api/auth/login", b"{not json",
                                       {})
        self.assertEqual(status, 400)
        self.assertIn("JSON", body["error"])

    def test_a_json_array_body_is_400(self):
        status, _ = self.api.handle("POST", "/api/auth/login", b"[1,2,3]", {})
        self.assertEqual(status, 400)

    def test_every_route_except_the_public_three_requires_a_token(self):
        """A guard against the next route being added without `auth`."""
        public = {"/api/auth/register", "/api/auth/login", "/api/health"}
        for route in self.api.routes:
            readable = route.pattern.pattern.strip("^$").replace(r"(?P<id>\d+)", "1")
            if not route.auth:
                self.assertIn(readable, public,
                              f"{readable} is public and is not on the allowed list")


# ====================================================================== seed

class TestSeedData(unittest.TestCase):
    """The seed is the demo dataset, so a broken seed is a broken demo."""

    @classmethod
    def setUpClass(cls):
        cls.store = BankStore()
        cls.svc = BankService(cls.store)
        cls.summary = seed_module.load(cls.svc)

    def test_it_loads_the_expected_volume(self):
        self.assertEqual(self.summary["users"], 14)
        self.assertEqual(self.summary["accounts"], 20)
        self.assertEqual(self.summary["transactions"], 73)

    def test_every_balance_matches_the_seed_document(self):
        """Replaying the ledger through this codebase reproduces figures that
        were computed independently. If these disagree, one of the two is wrong
        and it is worth finding out which before the demo."""
        for account_id, expected in seed_module.EXPECTED_BALANCES.items():
            with self.subTest(account=account_id):
                self.assertEqual(self.store.get_account(account_id).balance, expected)

    def test_everything_reconciles(self):
        self.assertEqual(self.svc.reconcile_all(), [])

    def test_the_account_numbers_match_the_document(self):
        """Account 11 is the float-precision canary; account 10 is the frozen one.
        The Postman collection references these numbers, so they must be stable."""
        self.assertEqual(self.store.get_account(10).status, "FROZEN")
        self.assertEqual(self.store.get_account(11).account_type, "CHECKING")
        self.assertEqual(self.store.get_account(4).balance, 0)

    def test_no_seeded_account_belongs_to_an_admin(self):
        """The two admins in the roster hold nothing. Accounts 8, 11 and 12 used
        to be theirs and were moved to customers rather than deleted, because the
        account numbers are positional and the document keys off them."""
        admins = {u.user_id for u in self.store.all_users() if u.is_admin}
        self.assertEqual(len(admins), 2)
        owned = [a.account_id for a in self.store.all_accounts()
                 if a.user_id in admins]
        self.assertEqual(owned, [])

    def test_seeding_twice_is_refused(self):
        with self.assertRaises(RuntimeError):
            seed_module.load(self.svc)


# ============================================================== live server

class TestLiveServer(unittest.TestCase):
    """One end-to-end pass over a real socket.

    Everything above tests `BankAPI.handle` directly, which skips the HTTP
    plumbing entirely - headers, status lines, Content-Length, JSON encoding. If
    that plumbing were broken, every test above would still pass and the server
    would not work. This class is the check that it does.
    """

    @classmethod
    def setUpClass(cls):
        store = BankStore()
        svc = BankService(store)
        cls.user = svc.register_user("Live Tester", "live@example.com",
                                     password_hash=SHARED_HASH)
        cls.account = svc.open_account(cls.user, "CHECKING", 25000)

        api = BankAPI(svc)
        # Port 0 asks the OS for any free port, so the suite never collides with
        # a server the developer already has running on 8000.
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        make_handler_class(api, quiet=True))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def call(self, method, path, body=None, token=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            # urllib raises on 4xx/5xx; the body is still the JSON we want.
            # `with` so the response is closed - an HTTPError holds an open
            # socket, and leaking it makes the suite print ResourceWarnings.
            with exc:
                return exc.code, json.loads(exc.read() or b"{}")

    def test_a_full_session_over_http(self):
        status, body = self.call("GET", "/api/health")
        self.assertEqual(status, 200)

        status, body = self.call("POST", "/api/auth/login",
                                 {"email": "live@example.com", "password": PASSWORD})
        self.assertEqual(status, 200)
        token = body["token"]

        status, body = self.call("POST", f"/api/accounts/{self.account.account_id}/deposit",
                                 {"amount": 4999}, token)
        self.assertEqual(status, 201)
        self.assertEqual(body["account"]["balance"], 29999)

        status, body = self.call("POST", f"/api/accounts/{self.account.account_id}/withdraw",
                                 {"amount": 1000000}, token)
        self.assertEqual(status, 409)

    def test_an_unauthenticated_request_gets_401_over_the_wire(self):
        status, _ = self.call("GET", "/api/accounts")
        self.assertEqual(status, 401)

    def test_cors_preflight_is_answered(self):
        """A browser sends OPTIONS before any cross-origin POST carrying an
        Authorization header, and abandons the real request if it is unanswered."""
        request = urllib.request.Request(self.base + "/api/accounts", method="OPTIONS")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")


if __name__ == "__main__":
    unittest.main(verbosity=2)
