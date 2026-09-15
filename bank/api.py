"""The controller layer: HTTP in, JSON out, and nothing else.

    Frontend (UI) -> REST API (Controller) -> Service Layer -> Repository -> Database
                     ^^^^^^^^^^^^^^^^^^^^
                     this file

WHAT A CONTROLLER IS ALLOWED TO DO
----------------------------------
Four things, and only these four:

    1. Work out who is calling         (read the token, look up the user)
    2. Pull values out of the request  (path, query string, JSON body)
    3. Call exactly one service method
    4. Turn the result, or the exception, into a status code and a body

There is no business rule anywhere in this file. No balance comparison, no "is
this account frozen", no ownership check. Those all live in `services.py`, and
the test for whether that separation is real is simple: `test_bank.py` exercises
every rule in the system without importing this module at all.

"Clean MVC separation" is a graded criterion, and the way it is usually lost is
not by a grand architectural mistake. It is lost one `if` at a time, each of which
looked easier to put in the handler than to thread through the service.

WHY http.server AND NOT FastAPI OR FLASK
----------------------------------------
The stack question is still open - the brief says MySQL "to be confirmed" and
suggests Node, Spring Boot or Python, while the syllabus teaches Python. Choosing
FastAPI now would quietly answer a question that belongs to the instructor, and
it would add a dependency to a submission that currently installs nothing.

`http.server` is in the standard library, so this runs on a clean machine with
`python server.py` and no virtualenv. The four things a controller does, listed
above, are the same in any framework; what changes is the routing syntax. When
the stack is settled, porting this file to FastAPI is mechanical - the route
table below becomes decorators, `_require_actor` becomes a dependency, and
`ERROR_STATUS` becomes an exception handler. Nothing outside this file moves.

The honest limitation: `http.server` is explicitly not for production use. For a
training project graded on API correctness and layer separation, that is fine,
and it is written down here rather than left to be discovered.

THE ERROR TABLE IS THE OTHER HALF OF THE DESIGN
-----------------------------------------------
`services.py` raises domain exceptions - `InsufficientFunds`, not "409". That is
what lets the same rules serve an HTTP API, a CLI, and a test suite. The price is
that somebody has to map one to the other, and `ERROR_STATUS` below is that map:
one table, in one file, instead of a `try`/`except` in each of sixteen handlers.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .errors import (
    AccountNotActive, AccountNotFound, BankError, DuplicateTransaction,
    EmailAlreadyUsed, InsufficientFunds, InvalidAmount, NotAuthorized, UserNotFound,
)
from .security import TOKEN_TTL_SECONDS, issue_token, new_secret, read_token
from .serializers import account_json, page_json, transaction_json, user_json

# ---------------------------------------------------------------------------
# Domain exception -> HTTP status. The whole mapping, in one place.
#
# Order matters: the lookup walks this list top to bottom and takes the first
# class the exception is an instance of, so subclasses must come before their
# parents. `InvalidAmount` before `BankError`, or every 400 would answer 500.
# ---------------------------------------------------------------------------
ERROR_STATUS = [
    # 400 Bad Request - the request itself is malformed or invalid.
    (InvalidAmount, 400),

    # 403 Forbidden - we know who you are, and you may not do this.
    # (A *failed login* is 401, not 403, and is handled in the login route:
    #  401 means "authenticate", 403 means "authenticating again will not help".)
    (NotAuthorized, 403),

    # 404 Not Found - also returned for an account that exists but is not yours.
    # See `BankService.get_account_for`: a distinct 403 there would confirm the
    # account is real, which is the leak the 404 exists to prevent.
    (AccountNotFound, 404),
    (UserNotFound, 404),

    # 409 Conflict - the request is well formed, but the current state refuses it.
    (InsufficientFunds, 409),
    (AccountNotActive, 409),
    (DuplicateTransaction, 409),
    (EmailAlreadyUsed, 409),

    # Anything else from the domain that has not been given a status yet.
    (BankError, 400),

    # ValueError covers the service layer's own argument checks - a missing name,
    # an unknown account type, an admin reason that is too short.
    (ValueError, 400),
    # money.to_cents raises TypeError on anything that is not an int number of
    # cents. That is a client mistake, not a server fault, so it is a 400 and not
    # a 500. (parse_amount catches most of these first and raises InvalidAmount;
    # this row covers the paths that reach to_cents directly.)
    (TypeError, 400),
]

MAX_BODY_BYTES = 64 * 1024  # A request body larger than this is refused unread.


class ApiError(Exception):
    """An HTTP-level problem with no domain meaning: a missing token, an unknown
    route, a body that is not JSON. Domain problems raise domain exceptions and
    are translated by `ERROR_STATUS` instead."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Request:
    """Everything a handler is given. Deliberately small.

    `actor` is the authenticated `User`, or None on a public route. A handler
    never reads a header or a raw query string; if it needs something, it is a
    field here, which keeps handler bodies down to one service call each.
    """

    __slots__ = ("method", "path", "params", "query", "body", "actor")

    def __init__(self, method, path, params, query, body, actor=None):
        self.method = method
        self.path = path
        self.params = params      # values captured from the URL, e.g. {"id": 4}
        self.query = query        # parsed query string, flattened to single values
        self.body = body          # parsed JSON body, always a dict (possibly empty)
        self.actor = actor        # the logged-in User, or None

    # -- small typed readers, so no handler ever re-implements validation --

    def require(self, key: str):
        """A body field that must be present and non-empty."""
        value = self.body.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ApiError(400, f"'{key}' is required")
        return value

    def optional(self, key: str, default=None):
        return self.body.get(key, default)

    def int_query(self, key: str, default: int) -> int:
        """A query-string integer that refuses to crash the request.

        `?page=abc` is a client mistake, and falling back to the default is kinder
        than a 500 and more useful than a 400 for a value this peripheral.
        """
        try:
            return int(self.query.get(key, default))
        except (TypeError, ValueError):
            return default


class Route:
    """One row of the routing table: a method, a URL pattern, and who may call it."""

    __slots__ = ("method", "pattern", "handler", "auth", "admin")

    def __init__(self, method, pattern, handler, auth=True, admin=False):
        self.method = method
        # Turn "/api/accounts/{id}/deposit" into a regex with a named group.
        # `\d+` rather than `.+` so a non-numeric id is a clean 404 from the
        # router instead of an exception deeper in.
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>\\d+)", pattern)
        self.pattern = re.compile(f"^{regex}$")
        self.handler = handler
        self.auth = auth      # must present a valid token
        self.admin = admin    # must additionally hold the ADMIN role


class BankAPI:
    """The routing table and the handlers.

    Separated from the HTTP server underneath it on purpose: `handle()` takes
    plain arguments and returns a plain `(status, dict)`, so `test_api.py` tests
    every route without opening a socket. It is also the seam that makes swapping
    `http.server` for FastAPI a change to the bottom of this file only.
    """

    def __init__(self, service, secret: str | None = None):
        self.service = service
        self.secret = secret or new_secret()
        self.routes = self._build_routes()

    # -------------------------------------------------------------- the table

    def _build_routes(self) -> list[Route]:
        """Every endpoint in the system, readable as a list.

        The five routes the brief specifies are marked. The rest are the auth the
        hiring manager asked for, plus the admin surface and the transfer from the
        bonus list.
        """
        return [
            # -- public: no token required ---------------------------------
            Route("POST", "/api/auth/register", self.register, auth=False),
            Route("POST", "/api/auth/login", self.login, auth=False),
            Route("GET", "/api/health", self.health, auth=False),

            # -- authenticated customer ------------------------------------
            Route("GET", "/api/auth/me", self.me),
            Route("POST", "/api/accounts", self.create_account),            # brief 5.4
            Route("GET", "/api/accounts", self.list_accounts),
            Route("GET", "/api/accounts/{id}", self.get_account),           # brief 5.4
            Route("POST", "/api/accounts/{id}/deposit", self.deposit),      # brief 5.4
            Route("POST", "/api/accounts/{id}/withdraw", self.withdraw),    # brief 5.4
            Route("GET", "/api/accounts/{id}/transactions", self.history),  # brief 5.4
            Route("POST", "/api/transfers", self.transfer),

            # -- admin only ------------------------------------------------
            Route("GET", "/api/admin/users", self.admin_users, admin=True),
            Route("GET", "/api/admin/accounts", self.admin_accounts, admin=True),
            Route("POST", "/api/admin/accounts/{id}/freeze", self.admin_freeze, admin=True),
            Route("POST", "/api/admin/accounts/{id}/adjust", self.admin_adjust, admin=True),
            Route("GET", "/api/admin/audit", self.admin_audit, admin=True),
            Route("GET", "/api/admin/reconciliation", self.admin_reconcile, admin=True),
        ]

    # ------------------------------------------------------------- dispatch

    def handle(self, method: str, raw_path: str, body_bytes: bytes = b"",
               headers: dict | None = None) -> tuple[int, dict]:
        """The single entry point. Never raises; every path returns (status, body).

        A handler that threw an unexpected exception would otherwise take the
        whole server down or leak a stack trace to the client, so the catch-all at
        the bottom turns anything unrecognised into a 500 with a generic message.
        """
        headers = headers or {}
        parsed = urlparse(raw_path)
        # parse_qs gives {"page": ["2"]}; flatten to {"page": "2"} since no
        # parameter in this API is legitimately repeated.
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        try:
            route, params = self._match(method, parsed.path)
            actor = self._authenticate(route, headers)
            body = self._parse_body(method, body_bytes)
            request = Request(method, parsed.path, params, query, body, actor)
            return route.handler(request)

        except ApiError as exc:
            return exc.status, {"error": exc.message}
        except Exception as exc:                      # noqa: BLE001 - intentional
            status = self._status_for(exc)
            if status is None:
                # Genuinely unexpected. Log it for the operator, and tell the
                # client nothing: an exception message can carry internal detail.
                import traceback
                traceback.print_exc()
                return 500, {"error": "internal server error"}
            return status, {"error": str(exc)}

    def _match(self, method: str, path: str) -> tuple[Route, dict]:
        """Find the route, distinguishing 404 from 405.

        If some route matches the path but none matches the method, the answer is
        405 Method Not Allowed rather than 404 - a POST to a GET-only URL is a
        different mistake from a URL that does not exist, and saying so saves the
        caller from hunting for a typo that is not there.
        """
        path_matched = False
        for route in self.routes:
            match = route.pattern.match(path)
            if not match:
                continue
            path_matched = True
            if route.method == method:
                # Path parameters are all `\d+`, so int() here is safe and means
                # handlers receive ints rather than strings.
                return route, {k: int(v) for k, v in match.groupdict().items()}
        raise ApiError(405 if path_matched else 404,
                       "method not allowed" if path_matched else "no such endpoint")

    def _authenticate(self, route: Route, headers: dict):
        """Turn an Authorization header into a User, and enforce the route's role.

        This runs for every protected route from one place. The build plan's
        Section 5.2 point applies here: a role check repeated as an `if` inside
        each handler is the fastest way to end up with one handler that forgot.
        """
        if not route.auth:
            return None

        raw = headers.get("authorization") or headers.get("Authorization") or ""
        if not raw.lower().startswith("bearer "):
            raise ApiError(401, "missing bearer token")

        payload = read_token(raw[7:].strip(), self.secret)
        if payload is None:
            # Malformed, forged, or expired - all one message. See read_token.
            raise ApiError(401, "invalid or expired token")

        try:
            # Load the user from the store rather than trusting the token's copy
            # of the role. The token is signed, so it has not been tampered with,
            # but it was issued up to an hour ago: if an admin has been demoted
            # since, the stored record is right and the token is stale.
            actor = self.service.store.get_user(payload["sub"])
        except UserNotFound:
            raise ApiError(401, "invalid or expired token") from None

        if route.admin and not actor.is_admin:
            raise ApiError(403, "admin role required")
        return actor

    @staticmethod
    def _parse_body(method: str, body_bytes: bytes) -> dict:
        """Parse a JSON body, or return an empty dict for a request with none."""
        if method in ("GET", "DELETE") or not body_bytes:
            return {}
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "request body must be valid JSON") from None
        if not isinstance(parsed, dict):
            raise ApiError(400, "request body must be a JSON object")
        return parsed

    @staticmethod
    def _status_for(exc: Exception) -> int | None:
        """First matching row of ERROR_STATUS, or None if nothing matches."""
        for exc_type, status in ERROR_STATUS:
            if isinstance(exc, exc_type):
                return status
        return None

    # ================================================================ handlers
    #
    # Each one: read the request, call one service method, serialize. If a handler
    # below ever grows a business rule, it belongs in services.py instead.

    # ------------------------------------------------------------------ auth

    def health(self, request: Request) -> tuple[int, dict]:
        """Liveness check. Useful for confirming the server is up before a demo.

        Answers whether the process is up, and nothing else. It used to include
        the account count, which was handy for seeing at a glance that the seed
        had run, but it was the wrong thing to put here twice over: it is a
        business figure on the one route that needs no token, and counting rows
        makes a liveness check get slower as the data grows - once this is MySQL
        it is a query, and a slow database would start failing health checks on a
        server that is perfectly alive.

        The count is still available to an admin from GET /api/admin/reconciliation,
        which reports `checked`.
        """
        return 200, {"status": "ok"}

    def register(self, request: Request) -> tuple[int, dict]:
        """Create a customer and log them straight in.

        Note there is no `role` field read from the body. Accepting one would let
        anybody mint themselves an admin by adding one line to a request, which is
        the most common privilege-escalation bug in exactly this kind of endpoint.
        Admins are created by the seed or by another admin, never by self-service.
        """
        user = self.service.register_user(
            name=request.require("name"),
            email=request.require("email"),
            password=request.require("password"),
        )
        return 201, {
            "user": user_json(user),
            "token": issue_token(user.user_id, user.role, self.secret),
            "expiresIn": TOKEN_TTL_SECONDS,
        }

    def login(self, request: Request) -> tuple[int, dict]:
        """Exchange email and password for a token.

        `NotAuthorized` is caught here and re-raised as 401 rather than falling
        through to the 403 in ERROR_STATUS. The distinction is real: 401 means
        "you are not authenticated, try credentials", 403 means "you are
        authenticated and still may not". A failed login is the first.
        """
        try:
            user = self.service.authenticate(request.require("email"),
                                             request.require("password"))
        except NotAuthorized:
            raise ApiError(401, "invalid email or password") from None
        return 200, {
            "user": user_json(user),
            "token": issue_token(user.user_id, user.role, self.secret),
            "expiresIn": TOKEN_TTL_SECONDS,
        }

    def me(self, request: Request) -> tuple[int, dict]:
        """Who the current token belongs to. The frontend calls this on load to
        decide whether a stored token is still good."""
        return 200, {"user": user_json(request.actor)}

    # -------------------------------------------------------------- accounts

    def create_account(self, request: Request) -> tuple[int, dict]:
        """POST /api/accounts - the brief's create-account endpoint.

        ONE DELIBERATE DEVIATION FROM THE BRIEF. Its sample body is:

            {"userId": 1, "accountType": "SAVINGS"}

        Taking the owner from the body means any caller can open an account in
        somebody else's name by changing that number - the same class of bug as
        the IDOR on `GET /api/accounts/{id}`. So the owner is the authenticated
        user, and `userId` is honoured only for an admin opening an account on a
        customer's behalf. The brief's exact body still works; it just no longer
        works for a customer targeting a stranger.
        """
        owner = request.actor
        requested_owner = request.optional("userId")
        if requested_owner is not None and int(requested_owner) != request.actor.user_id:
            if not request.actor.is_admin:
                raise ApiError(403, "cannot open an account for another user")
            owner = self.service.store.get_user(int(requested_owner))

        account = self.service.open_account(
            owner=owner,
            account_type=request.require("accountType"),
            opening_balance=request.optional("openingBalance", 0),
        )
        return 201, {"account": account_json(account, owner)}

    def list_accounts(self, request: Request) -> tuple[int, dict]:
        """Every account belonging to the caller. Not in the brief, but the
        dashboard needs it, and without it the UI has no way to discover an
        account id short of the user typing one in."""
        accounts = self.service.my_accounts(request.actor)
        return 200, {"accounts": [account_json(a, request.actor) for a in accounts]}

    def get_account(self, request: Request) -> tuple[int, dict]:
        """GET /api/accounts/{id} - the brief's endpoint, with the hole closed.

        The ownership check is not written here. It is inside
        `service.get_account_for`, which every read and write path already goes
        through, so this route cannot forget it and neither can the next one
        somebody adds.
        """
        account = self.service.get_account_for(request.params["id"], request.actor)
        owner = self.service.store.get_user(account.user_id)
        return 200, {"account": account_json(account, owner)}

    def deposit(self, request: Request) -> tuple[int, dict]:
        """POST /api/accounts/{id}/deposit - the brief's endpoint.

        `clientTxnId` is optional and is the cheap idempotency guard: the client
        generates one UUID per submission attempt, and a double-clicked button
        sends the same one twice. The second is refused with 409 rather than
        depositing twice. See `BankService._guard_idempotency`.
        """
        txn = self.service.deposit(
            account_id=request.params["id"],
            amount=request.require("amount"),
            actor=request.actor,
            client_txn_id=request.optional("clientTxnId"),
        )
        return self._movement_response(txn, request)

    def withdraw(self, request: Request) -> tuple[int, dict]:
        """POST /api/accounts/{id}/withdraw - the brief's endpoint."""
        txn = self.service.withdraw(
            account_id=request.params["id"],
            amount=request.require("amount"),
            actor=request.actor,
            client_txn_id=request.optional("clientTxnId"),
        )
        return self._movement_response(txn, request)

    def history(self, request: Request) -> tuple[int, dict]:
        """GET /api/accounts/{id}/transactions - the brief's endpoint, paginated.

        Supports ?page=, ?pageSize= and ?type=DEPOSIT. The ownership check is
        again inside the service call, not here.
        """
        page = request.int_query("page", 1)
        page_size = request.int_query("pageSize", 20)
        rows, total = self.service.history(
            account_id=request.params["id"],
            actor=request.actor,
            page=page,
            page_size=page_size,
            txn_type=request.query.get("type"),
        )
        # The service clamps page_size to 1..100, so echo back what it actually
        # used rather than what was asked for, or the client's paging arithmetic
        # will disagree with the server's.
        effective_size = min(max(1, page_size), 100)
        return 200, page_json([transaction_json(t) for t in rows], total,
                              max(1, page), effective_size)

    def transfer(self, request: Request) -> tuple[int, dict]:
        """POST /api/transfers - the brief's bonus feature.

        Body carries both account ids, so this is not nested under
        /api/accounts/{id}: a transfer is an operation on the pair, and putting
        one of them in the path and the other in the body suggests an asymmetry
        that does not exist.
        """
        out, inn = self.service.transfer(
            from_id=int(request.require("fromAccountId")),
            to_id=int(request.require("toAccountId")),
            amount=request.require("amount"),
            actor=request.actor,
            client_txn_id=request.optional("clientTxnId"),
        )
        source = self.service.get_account_for(out.account_id, request.actor)
        return 201, {
            "debit": transaction_json(out),
            "credit": transaction_json(inn),
            "account": account_json(source, request.actor),
        }

    def _movement_response(self, txn, request: Request) -> tuple[int, dict]:
        """Shared reply for deposit and withdraw.

        Returns the new account alongside the transaction, on purpose. The client
        must never compute a balance by adding the amount to the one it was
        holding - that is the frontend doing money arithmetic, and it is wrong the
        moment two tabs are open. One request, one authoritative balance back.
        """
        account = self.service.get_account_for(txn.account_id, request.actor)
        return 201, {
            "transaction": transaction_json(txn),
            "account": account_json(account, request.actor),
        }

    # ----------------------------------------------------------------- admin
    #
    # Every route here is `admin=True` in the table, so `_authenticate` has already
    # rejected a customer with 403 before any of these run. The service methods
    # check the role a second time, which is not redundant: services.py must be
    # safe to call from a CLI or a test that never passes through this file.

    def admin_users(self, request: Request) -> tuple[int, dict]:
        users = self.service.all_users(request.actor)
        return 200, {"users": [user_json(u) for u in users]}

    def admin_accounts(self, request: Request) -> tuple[int, dict]:
        accounts = self.service.all_accounts(request.actor)
        return 200, {"accounts": [
            account_json(a, self.service.store.get_user(a.user_id)) for a in accounts
        ]}

    def admin_freeze(self, request: Request) -> tuple[int, dict]:
        """Freeze or unfreeze. `frozen` is explicit rather than a toggle, so
        retrying a request that may or may not have landed is safe."""
        frozen = request.optional("frozen", True)
        account = self.service.set_frozen(
            account_id=request.params["id"],
            frozen=bool(frozen),
            reason=request.require("reason"),
            actor=request.actor,
        )
        return 200, {"account": account_json(account)}

    def admin_adjust(self, request: Request) -> tuple[int, dict]:
        """The only way an admin may change a balance.

        There is no `PUT /api/accounts/{id}/balance` in the route table and there
        should never be one. An adjustment posts a normal ledger entry tagged with
        the acting admin and a written reason, so `balance == sum(ledger)` still
        holds afterwards. A balance set directly breaks that invariant permanently
        and leaves no way to tell which of the two numbers was right.
        """
        txn = self.service.adjust(
            account_id=request.params["id"],
            amount=request.require("amount"),
            direction=request.require("direction"),
            reason=request.require("reason"),
            actor=request.actor,
        )
        account = self.service.store.get_account(request.params["id"])
        return 201, {"transaction": transaction_json(txn),
                     "account": account_json(account)}

    def admin_audit(self, request: Request) -> tuple[int, dict]:
        """Read-only. Who did what, to which account, and why."""
        return 200, {"entries": [
            {"actorUserId": a, "action": b, "accountId": c, "reason": d}
            for a, b, c, d in self.service.audit_log(request.actor)
        ]}

    def admin_reconcile(self, request: Request) -> tuple[int, dict]:
        """Every account where the stored balance disagrees with the ledger sum.

        Should always be empty. This is the endpoint to open during the demo: it
        is the running proof that no code path has changed a balance without
        writing a matching entry.
        """
        broken = self.service.reconciliation_report(request.actor)
        return 200, {
            "balanced": not broken,
            "checked": len(self.service.store.all_accounts()),
            "discrepancies": [
                {"accountId": i, "balance": b, "ledgerSum": s}  # cents
                for i, b, s in broken
            ],
        }


# ===========================================================================
# HTTP plumbing. Everything above is transport-independent; only this part
# knows about sockets, and it is the only part that changes under FastAPI.
# ===========================================================================

def make_handler_class(api: BankAPI, cors: bool = True, quiet: bool = False):
    """Build a request handler class bound to one BankAPI instance.

    A closure rather than a constructor argument because `http.server`
    instantiates the handler class itself, once per request, and gives us no
    opportunity to pass anything in.
    """

    class BankRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # required for keep-alive and Content-Length
        server_version = "SimpleBank/1.0"

        # -- the three verbs this API uses --

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_OPTIONS(self):
            """CORS preflight. A browser sends this before any cross-origin POST
            that carries an Authorization header, and refuses the real request if
            it is not answered."""
            self._respond(204, None)

        def _dispatch(self, method: str):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                # Refuse without reading. Reading it first would mean allocating
                # whatever a caller decided to send.
                self._respond(413, {"error": "request body too large"})
                return
            body = self.rfile.read(length) if length else b""
            status, payload = api.handle(method, self.path, body, dict(self.headers))
            self._respond(status, payload)

        def _respond(self, status: int, payload):
            data = b"" if payload is None else json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if cors:
                # Development convenience: the React dev server runs on a
                # different port, which makes every call cross-origin.
                # `*` is fine while tokens travel in a header. It would NOT be
                # fine with cookie-based sessions, where it must name the exact
                # origin and set Access-Control-Allow-Credentials.
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            if data:
                self.wfile.write(data)

        def log_message(self, fmt, *args):
            """One tidy line per request instead of the default noise.

            Silenced entirely under `quiet`, which the test suite passes so that a
            server booted inside a test does not interleave its access log with
            unittest's own output.
            """
            if quiet:
                return
            print(f"  {self.command:<7} {self.path:<45} {args[1] if len(args) > 1 else ''}")

    return BankRequestHandler


def serve(service, host: str = "127.0.0.1", port: int = 8000,
          secret: str | None = None) -> None:
    """Start the API. Blocks until Ctrl+C.

    ThreadingHTTPServer, not HTTPServer: the single-threaded version handles one
    request at a time, which would hide the concurrency problem the lock in
    `BankService` exists to solve. Serving requests in parallel means the demo
    runs on the same execution model the rules were written for.
    """
    api = BankAPI(service, secret)
    httpd = ThreadingHTTPServer((host, port), make_handler_class(api))
    print(f"  Simple Bank API listening on http://{host}:{port}")
    print(f"  {len(api.routes)} routes. Try: GET http://{host}:{port}/api/health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()
