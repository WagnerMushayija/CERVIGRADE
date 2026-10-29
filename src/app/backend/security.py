"""Passwords and login tokens. Standard library plus PyJWT, nothing that needs a compiler."""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

_ITERATIONS = 200_000
TOKEN_HOURS = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def load_secret(data_dir: str) -> str:
    """CERVIGRADE_SECRET if set, otherwise a random key that is created once and kept in the data folder."""
    env = os.environ.get("CERVIGRADE_SECRET")
    if env:
        return env
    path = os.path.join(data_dir, "secret.key")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read().strip()
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def make_token(user_id: int, key: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, key, algorithm="HS256")


def read_token(token: str, key: str):
    """The user id inside a valid, unexpired token, or None."""
    try:
        return int(jwt.decode(token, key, algorithms=["HS256"])["sub"])
    except Exception:
        return None
