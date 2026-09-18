"""Run the API on AWS Lambda, behind API Gateway or a Function URL.

WHY THIS FILE IS SHORT. `bank/api.py` keeps `BankAPI.handle()` free of any
transport: it takes a method, a path, some bytes and some headers, and returns
`(status, dict)`. That is the seam its docstring promises, so serving the same
API from Lambda is a translation of one event shape into those four arguments
and back - not a second implementation of anything.

`server.py` is the other caller of that seam. Neither knows about the other, and
the routing table, the auth and the error mapping are shared by both.

WHAT LAMBDA CHANGES, AND WHY THE ENVIRONMENT IS NOT OPTIONAL. Locally,
`server.py` is one long-lived process that may invent a signing key and hold the
bank in memory. Lambda is neither long-lived nor single: containers are frozen,
thawed and replaced, and several run at once.

    BANK_SECRET   Required. Without it `BankAPI` calls `new_secret()` and each
                  container signs with a different key, so a token minted by one
                  is rejected by the next - you log in, and the very next request
                  401s. It must also be set rather than generated because
                  `ensure_secret()` writes to `.env`, and only /tmp is writable
                  here.
    MONGODB_URI   Required, with MONGODB_DB. The in-memory store dies with the
    MONGODB_DB    container, and two containers would hold two different banks.

Set MONGODB_DB to your own database, never the shared `simple_bank`.
"""
import base64
import json
import os

from bank import BankAPI, BankService

# Answered on every response. `*` is safe while the token travels in a header
# and not a cookie - the same reasoning as `make_handler_class` in bank/api.py.
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
}

# Built on the first request and kept for the life of the container. A Mongo
# client opens a connection pool and a background monitor thread, so building
# one per invocation would spend more time connecting than answering - and, at
# any real rate of requests, would open connections faster than Atlas closes
# them.
_api = None


def _build():
    """Construct the API, or raise with something an operator can act on."""
    uri = os.environ.get("MONGODB_URI", "").strip()
    db_name = os.environ.get("MONGODB_DB", "").strip()
    secret = os.environ.get("BANK_SECRET", "").strip()

    # Checked together so a misconfigured function reports everything that is
    # wrong on the first request, rather than one variable per deploy.
    missing = [name for name, value in
               (("MONGODB_URI", uri), ("MONGODB_DB", db_name), ("BANK_SECRET", secret))
               if not value]
    if missing:
        raise RuntimeError("missing environment variables: " + ", ".join(missing))

    from bank.mongo_store import MongoStore

    return BankAPI(
        BankService(MongoStore(uri, db_name)),
        secret=secret,
        # Absent means admin registration is shut, which is the right default for
        # a deployed function: see `api._role_for`.
        admin_code=os.environ.get("BANK_ADMIN_CODE", "").strip() or None,
    )


def _request(event):
    """(method, path-with-query, body bytes, headers) from either payload format.

    Both are accepted because the format is chosen by the trigger, not by us: an
    HTTP API and a Function URL send 2.0, a REST API sends 1.0, and picking one
    would turn a console default into a silent 500.
    """
    context = event.get("requestContext") or {}
    if "http" in context:                                   # payload format 2.0
        method = context["http"]["method"]
        path = event.get("rawPath") or "/"
        query = event.get("rawQueryString") or ""
    else:                                                   # payload format 1.0
        method = event.get("httpMethod") or "GET"
        path = event.get("path") or "/"
        query = ""
        params = event.get("queryStringParameters") or {}
        if params:
            from urllib.parse import urlencode
            query = urlencode(params)

    if query:
        path = f"{path}?{query}"

    # A binary body arrives base64-encoded. Ours is always JSON, but the flag is
    # set by the gateway's own content-type rules rather than by the client.
    raw = event.get("body") or ""
    body = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")

    return method, path, body, event.get("headers") or {}


def _response(status, payload):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8", **CORS},
        "body": "" if payload is None else json.dumps(payload),
    }


def lambda_handler(event, context):
    global _api

    method, path, body, headers = _request(event)

    # The preflight a browser sends before any cross-origin request carrying an
    # Authorization header. It is answered before anything else because the route
    # table holds no OPTIONS row - `handle` would correctly call it a 405, and
    # the browser would then refuse the real request.
    if method == "OPTIONS":
        return _response(204, None)

    if _api is None:
        try:
            _api = _build()
        except Exception as exc:                            # noqa: BLE001
            # Configuration and connection failures are the two things that go
            # wrong on a fresh deployment, and a 502 from a crashed init tells
            # nobody which. Say it in the response, and log it for CloudWatch.
            print(f"startup failed: {exc}")
            return _response(503, {"error": f"service unavailable: {exc}"})

    # `handle` never raises: every path, including an unexpected exception,
    # comes back as a status and a JSON body.
    status, payload = _api.handle(method, path, body, headers)
    return _response(status, payload)
