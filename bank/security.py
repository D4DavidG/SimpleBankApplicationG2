"""Password hashing and session token generation. Standard library only.

Two jobs, both of which are easy to get dangerously wrong, so both live in one
small file that can be read end to end in a minute.

    hash_password / verify_password   -> storing a password safely
    new_token                         -> the random string a session is named by

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

WHY AN OPAQUE RANDOM TOKEN AND NOT A JWT
----------------------------------------
This file used to mint a signed token that carried the user id and role in its
payload - a JWT reduced to its load-bearing parts, since PyJWT is a third-party
package. It carried no state, which is its selling point and also its problem: a
token that the server never recorded is a token the server cannot revoke, and
logging out could only mean "the browser forgets it".

The token is now a random string and nothing else. The user id and the expiry
live in a `tokens` table alongside it, so a session is a row: it can be looked
up, expired, listed, or deleted. See `BankService.issue_token` for the write and
`BankService.validate_token` for the read.

Because the token carries no meaning, there is nothing in it to forge. Guessing
one means guessing 256 bits of `secrets` output, which is the same bet as
guessing an HMAC key. What this does cost is a database read on every
authenticated request - the honest trade for a session the server actually holds.
"""
import base64
import binascii
import hashlib
import hmac
import secrets

# Cost factor. Higher is slower, and slow is the entire point: it is what makes
# guessing a stolen hash expensive. This is roughly the OWASP floor for
# PBKDF2-HMAC-SHA256. Raising it later is safe, because the round count is stored
# inside each hash, so existing hashes keep verifying with the number they were
# created with.
PBKDF2_ROUNDS = 600_000
SALT_BYTES = 16

# One week. Long for a bank, and chosen for a graded demo rather than for a real
# one: an hour meant a token saved in Postman, or a tab left open over a weekend,
# came back 401 in the middle of showing something. The token is revocable now -
# it is a row - so length costs less than it did when nothing could cancel it.
# A real deployment shortens this and adds a refresh; see README §13.
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
# 32 bytes of randomness, base64url-encoded to 43 characters. Well past the 128
# bits OWASP asks of a session id, and `secrets` is the cryptographic generator -
# never `random`, whose output is reproducible from a few observed values.
TOKEN_BYTES = 32


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

def new_token() -> str:
    """A fresh session token: `TOKEN_BYTES` of randomness, URL and header safe.

    Unpredictable is the only property required of it. It is not derived from the
    user, the time, or anything else a caller could observe or guess - two logins
    by the same person a millisecond apart produce unrelated strings, and neither
    reveals anything about the other.

    Uniqueness is not checked here, and does not need to be: a collision between
    two 256-bit random values will not happen, and the token column is the
    primary key, so if one ever did the insert would be refused rather than
    quietly handing one person another person's session.
    """
    return secrets.token_urlsafe(TOKEN_BYTES)
