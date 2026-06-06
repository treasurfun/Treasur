"""Lightweight auth: signed bearer tokens (HMAC) carrying a subject claim.

A user authenticates with their wallet address + a password they set; the
backend issues a token. The admin uses ADMIN_PASSWORD. This is intentionally
simple file-backed auth, not an identity provider.
"""
import hashlib
import hmac
import json
import time
import base64

from fastapi import Header, HTTPException, Depends

from config import get_settings

_settings = get_settings()


def _sign(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(_settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def issue_token(subject: str, is_admin: bool = False, ttl: int = 86400) -> str:
    return _sign({"sub": subject, "admin": is_admin, "exp": int(time.time()) + ttl})


def _verify(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(_settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return _verify(authorization[7:])


def require_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    return user
