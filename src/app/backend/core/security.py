"""Passwords and login tokens. Standard library plus PyJWT, nothing that needs a compiler."""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt


class PasswordHasher:
    """Turns a password into a salted PBKDF2 hash and checks a password against a stored hash. Passwords are never stored."""

    def __init__(self, iterations=200_000):
        self.iterations = iterations

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.iterations)
        return f"pbkdf2_sha256${self.iterations}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, stored: str) -> bool:
        try:
            scheme, iterations, salt_hex, digest_hex = stored.split("$")
            if scheme != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
            return hmac.compare_digest(digest.hex(), digest_hex)
        except Exception:
            return False


class TokenService:
    """Makes and reads the signed login tokens (JWT) that the page sends with every request."""

    def __init__(self, secret: str, hours: int = 8):
        self._secret = secret
        self.hours = hours

    def make(self, user_id: int) -> str:
        exp = datetime.now(timezone.utc) + timedelta(hours=self.hours)
        return jwt.encode({"sub": str(user_id), "exp": exp}, self._secret, algorithm="HS256")

    def read(self, token: str):
        """The user id inside a valid, unexpired token, or None."""
        try:
            return int(jwt.decode(token, self._secret, algorithms=["HS256"])["sub"])
        except Exception:
            return None


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


_hasher = PasswordHasher()
hash_password = _hasher.hash            # short names for code that only needs the default hasher
verify_password = _hasher.verify
