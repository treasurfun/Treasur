"""Privy authentication helpers.

  1. verify_token(access_token) — verifies the Privy access-token JWT against the
     app's public verification key (a PEM if PRIVY_VERIFICATION_KEY is set, else
     fetched via the app's JWKS endpoint), checking issuer 'privy.io' and audience
     = our app id. Returns the user's DID (the token's `sub`).
  2. fetch_user(did) — calls Privy's REST API (HTTP Basic auth with app id : app
     secret) to read the user's linked accounts, returning their Solana wallet
     address and X/Twitter handle.

The app secret is only ever read from config (the environment) and is never logged.
"""
import base64

import httpx
import jwt
from jwt import PyJWKClient

from config import get_settings

_settings = get_settings()
_jwks_client = None


def _jwks_url() -> str:
    if _settings.PRIVY_JWKS_URL:
        return _settings.PRIVY_JWKS_URL
    return f"{_settings.PRIVY_API_BASE}/apps/{_settings.PRIVY_APP_ID}/jwks.json"


def _signing_key(token: str):
    if _settings.PRIVY_VERIFICATION_KEY:
        return _settings.PRIVY_VERIFICATION_KEY.replace("\\n", "\n").encode()
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_jwks_url())
    return _jwks_client.get_signing_key_from_jwt(token).key


def verify_token(access_token: str) -> str:
    """Verify the Privy access token; return the user's DID. Raises if invalid."""
    key = _signing_key(access_token)
    claims = jwt.decode(
        access_token,
        key,
        algorithms=["ES256", "EdDSA"],
        issuer="privy.io",
        audience=_settings.PRIVY_APP_ID,
        options={"require": ["exp", "iat", "sub"]},
    )
    sub = claims.get("sub")
    if not sub:
        raise ValueError("token missing subject (sub)")
    return sub


def _basic_auth_header() -> str:
    raw = f"{_settings.PRIVY_APP_ID}:{_settings.PRIVY_APP_SECRET}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def fetch_user(did: str) -> dict:
    """Fetch a Privy user by DID. Returns {'wallet': <solana addr or ''>, 'twitter': <handle or ''>}."""
    if not _settings.PRIVY_APP_SECRET:
        raise RuntimeError("PRIVY_APP_SECRET is not set")
    url = f"{_settings.PRIVY_API_BASE}/users/{did}"
    headers = {
        "Authorization": _basic_auth_header(),
        "privy-app-id": _settings.PRIVY_APP_ID,
        "Content-Type": "application/json",
    }
    r = httpx.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    accounts = data.get("linked_accounts", []) or []

    sol_wallet = ""
    any_wallet = ""
    twitter = ""
    for a in accounts:
        t = (a.get("type") or "").lower()
        if "wallet" in t:
            chain = (a.get("chain_type") or a.get("chainType") or "").lower()
            addr = a.get("address") or ""
            if not addr:
                continue
            if chain == "solana" and not sol_wallet:
                sol_wallet = addr
            elif not any_wallet:
                any_wallet = addr
        elif "twitter" in t or "x_oauth" in t:
            twitter = a.get("username") or a.get("handle") or a.get("name") or ""

    return {"wallet": sol_wallet or any_wallet, "twitter": (twitter or "").lstrip("@").strip()}
