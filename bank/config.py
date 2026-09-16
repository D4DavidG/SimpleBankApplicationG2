"""Reading `.env`, without a dependency.

`.env.example` has documented `BANK_SECRET` since the first commit and told
people to copy it to `.env`, and until now nothing actually read that file -
`security.py` reads `os.environ` directly, so `.env` was documentation that
looked like configuration. Anyone who put a value in it and wondered why nothing
changed was right to be confused.

WHY NOT python-dotenv
---------------------
The format we need is `KEY=value`, one per line, with comments. That is the
whole of it. The library handles variable interpolation, multiline values and
export syntax, none of which appear in our file, and pulling in a dependency for
thirty lines is a worse trade than writing the thirty lines - especially in a
project whose backend is otherwise standard library only.

PRECEDENCE
----------
A real environment variable always wins over the file. That is the conventional
direction and it is what makes

    MONGODB_DB=simple_bank_test python server.py --mongo

work without editing anything. The file is the default, not the override.
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# Set once per process. Calling load_env() from several entry points - the
# server, the seeder, the checker - must not re-read the file each time.
_loaded = False


def load_env(path: Path | None = None, override: bool = False) -> dict[str, str]:
    """Read `.env` into `os.environ`. Returns what was found in the file.

    Missing file is not an error: the whole project is designed to run with no
    environment at all, and that stays true.
    """
    global _loaded
    env_path = path or ENV_FILE
    found: dict[str, str] = {}

    if not env_path.exists():
        _loaded = True
        return found

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key:
            continue
        # Tolerate quotes. People copy these lines out of shell snippets, where
        # the quotes are load-bearing, into a file where they are not.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[key] = value
        if override or key not in os.environ:
            os.environ[key] = value

    _loaded = True
    return found


def ensure_loaded() -> None:
    """Load once, for callers that do not care whether it happened already."""
    if not _loaded:
        load_env()


def mongo_uri() -> str | None:
    ensure_loaded()
    return os.environ.get("MONGODB_URI") or None


def mongo_db_name(default: str = "simple_bank") -> str:
    ensure_loaded()
    return os.environ.get("MONGODB_DB") or default
