"""Authentication utilities for the hub server.

Password hashing with argon2, JWT token creation and validation.
"""

from __future__ import annotations

import os
import time
import uuid

import argon2
import jwt

_hasher = argon2.PasswordHasher()

# In production this should come from env vars / config
_jwt_secret = os.environ.get("CHENEDUSYS_JWT_SECRET", "change-me-in-production")
_jwt_algorithm = "HS256"
_jwt_expiry_seconds = 86400  # 24 hours


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False


def create_token(user_id: str, username: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + _jwt_expiry_seconds,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _jwt_secret, algorithm=_jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None if invalid."""
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=[_jwt_algorithm])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def new_id() -> str:
    return uuid.uuid4().hex[:12]
