"""
auth.py — JWT authentication helpers for FactAgent API.

Dependencies:
  passlib[bcrypt]          — secure password hashing
  python-jose[cryptography] — JWT encoding / decoding

Environment variables:
  JWT_SECRET_KEY   — secret used to sign tokens (required in production)
  JWT_ALGORITHM    — signing algorithm, default HS256
  JWT_EXPIRE_DAYS  — token lifetime in days, default 7
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "INSECURE_DEV_SECRET_CHANGE_ME_IN_PRODUCTION")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

# ── Crypto context ────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl points to the login endpoint; auto_error=False → anonymous OK
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return pwd_context.verify(plain, hashed)


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_access_token(user_id: int, username: str) -> str:
    """Create a signed JWT containing the user ID and username."""
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT. Returns the payload dict or None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ── FastAPI dependencies ───────────────────────────────────────────────────────

def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    """
    Optional auth dependency.

    - If no token is supplied → returns None (anonymous request).
    - If a token is supplied but invalid → raises 401.
    - If valid → returns the decoded JWT payload dict.
    """
    if token is None:
        return None
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_current_user(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """
    Strict auth dependency — raises 401 if the request is not authenticated.
    Use on endpoints that must have a logged-in user.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
