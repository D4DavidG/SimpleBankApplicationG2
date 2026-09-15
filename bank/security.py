"""Password hashing and session tokens. Standard library only.

Two jobs, both of which are easy to get dangerously wrong, so both live in one
small file that can be read end to end in a minute.

    hash_password / verify_password   -> storing a password safely
    issue_token / read_token          -> proving who you are on the next request

WHY PBKDF2 AND NOT bcrypt
-------------------------
The build plan says bcrypt or argon2 through a library, and that is still the
right answer for production. Neither is in the Python standard library, and this
submission has a hard "nothing to pip install" constraint, so this file uses
`hashlib.pbkdf2_hmac`, which *is* in the standard library and *is* a real
password-based key derivation function: salted, and deliberately slow.

What matters is that the shape is identical. `hash_password` returns one opaque
string and `verify_password` takes that string back, so swapping in bcrypt later
means rewriting the bodies of two functions and nothing else. The one thing that
is never acceptable, in any of these variants, is a bare SHA-256 of the password:
a plain hash is fast, and fast is exactly the property an attacker wants.

WHY A HAND-ROLLED TOKEN AND NOT A JWT
-------------------------------------
Same reason: PyJWT is a third-party package. The token below is the same idea as
a JWT reduced to its load-bearing parts - a JSON payload, base64url-encoded,
followed by an HMAC-SHA256 signature over that payload. Because the server signs
with a secret only it holds, a client can read the payload but cannot change it
without invalidating the signature.

The critical detail is in `read_token`: the signature is checked BEFORE the
payload is trusted, using `hmac.compare_digest`. A normal `==` on two byte
strings returns as soon as it finds a difference, so how long it takes leaks how
much of a guess was correct. `compare_digest` takes the same time either way.
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time

# Cost factor. Higher is slower, and slow is the entire point: it is what makes
# guessing a stolen hash expensive. This is roughly the OWASP floor for
# PBKDF2-HMAC-SHA256. Raising it later is safe, because the round count is stored
# inside each hash, so existing hashes keep verifying with the number they were
# created with.
PBKDF2_ROUNDS = 600_000
SALT_BYTES = 16
TOKEN_TTL_SECONDS = 60 * 60  # 1 hour. Short-lived on purpose; see the README.


# --------------------------------------------------------------------- helpers

def _b64encode(raw: bytes) -> str:
    """base64url with the `=` padding stripped, so the result is URL and header safe."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    """Inverse of `_b64encode`. Puts back however much padding was removed."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


# ------------------------------------------------------------------- passwords

def hash_password(password: str, rounds: int = PBKDF2_ROUNDS) -> str:
    """Derive a storable representation of a password.

    Returns a single self-describing string:

        pbkdf2_sha256$600000$<salt-b64>$<derived-key-b64>

    Everything needed to verify a later guess is in that string, including the
    round count and the salt. That is why no other column is needed, and why the
    cost factor can be raised without invalidating existing users.

    The salt is fresh random bytes per user. Two people who choose the same
    password get different stored values, which is what stops one cracked hash
    from unlocking every account that shares that password.
    """
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("password must be a string of at least 8 characters")
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${_b64encode(salt)}${_b64encode(derived)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Check a guess against a stored hash. Never raises; returns True or False.

    `encoded` is allowed to be None, which is the case for a user created without
    a password. That user simply cannot log in, and this returns False rather
    than crashing the login route.
    """
    if not encoded or not isinstance(password, str):
        return False
    try:
        algorithm, rounds, salt_b64, expected_b64 = encoded.split("$")
    except ValueError:
        return False  # malformed stored value; treat as "does not verify"
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64decode(salt_b64), int(rounds)
        )
        expected = _b64decode(expected_b64)
    except (ValueError, binascii.Error):
        return False
    # Constant-time comparison. See the module docstring.
    return hmac.compare_digest(derived, expected)


# ---------------------------------------------------------------------- tokens

def new_secret() -> str:
    """The server's signing key.

    Read from the BANK_SECRET environment variable when it is set, otherwise a
    fresh random value per process. The random default is the safe one for a demo
    - no secret is ever committed - and it means restarting the server
    invalidates every issued token, which is worth knowing before you wonder why
    a saved Postman token stopped working.
    """
    return os.environ.get("BANK_SECRET") or secrets.token_urlsafe(32)


def issue_token(user_id: int, role: str, secret: str,
                ttl: int = TOKEN_TTL_SECONDS) -> str:
    """Mint a signed session token for a user who has just proved who they are.

    The payload carries the user id, their role, and an absolute expiry. It is
    signed, not encrypted: anyone holding the token can read those three fields.
    That is acceptable because none of them are secret; what matters is that they
    cannot be *changed*. Nothing sensitive ever goes in here.
    """
    payload = {"sub": user_id, "role": role, "exp": int(time.time()) + ttl}
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"),
                         hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def read_token(token: str, secret: str) -> dict | None:
    """Validate a token and return its payload, or None if it is not usable.

    "Not usable" deliberately collapses several cases into one answer - malformed,
    wrong signature, expired - because the caller's response is the same 401 in
    every case, and distinguishing them out loud tells an attacker which part of
    their forgery to fix.

    Order matters: verify the signature FIRST, then parse. Parsing untrusted bytes
    before checking that they came from us means acting on attacker-supplied
    structure.
    """
    if not token or "." not in token:
        return None
    body, _, signature_b64 = token.partition(".")
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"),
                        hashlib.sha256).digest()
    try:
        provided = _b64decode(signature_b64)
    except (ValueError, binascii.Error):
        return None
    if not hmac.compare_digest(expected, provided):
        return None  # signature does not match: forged or tampered with
    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, binascii.Error):
        return None
    if not isinstance(payload, dict) or "sub" not in payload:
        return None
    if payload.get("exp", 0) < time.time():
        return None  # expired; the client must log in again
    return payload
