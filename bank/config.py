"""Configuration loading. Standard library only.

Reads KEY=value lines from `.env` into the environment, so the server picks up
MONGODB_URI, MONGODB_DB and BANK_SECRET without a third-party loader. A value
already set in the real environment wins over the file, which lets a one-off
command override it.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> bool:
    """Load `.env` into os.environ. Returns whether a file was found.

    Blank lines and lines starting with # are ignored. Matching quotes around a
    value are stripped, since people copy these out of shell snippets.
    """
    env_file = Path(path) if path is not None else PROJECT_ROOT / ".env"
    if not env_file.exists():
        return False
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return True
