"""Password hashing (pbkdf2, no native deps) and JWT tokens (demo-grade, ADR-009)."""
import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt

from .config import get_settings

settings = get_settings()

_PBKDF2_ITERS = 100_000


def hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = base64.b64encode(os.urandom(16)).decode()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, _iters, salt, _digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def create_access_token(sub: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
