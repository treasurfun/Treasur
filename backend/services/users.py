"""File-backed user store with salted PBKDF2 password hashing (stdlib only).

Users are keyed by their Solana wallet address. Passwords are never stored in
plaintext — only a per-user random salt + PBKDF2-HMAC-SHA256 hash. This replaces
the previous insecure login that accepted any password.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from config import get_settings

_settings = get_settings()
_lock = threading.RLock()
_PATH = os.path.join(_settings.DATA_DIR, "users.json")
_PBKDF2_ROUNDS = 200_000
_B58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def _load() -> dict:
    if not os.path.exists(_PATH):
        return {}
    with open(_PATH) as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(_settings.DATA_DIR, exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, _PATH)


def valid_wallet(w: str) -> bool:
    return 32 <= len(w) <= 44 and all(c in _B58 for c in w)


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS).hex()


def register(name: str, wallet: str, password: str) -> None:
    wallet = wallet.strip()
    if not valid_wallet(wallet):
        raise ValueError("Invalid Solana wallet address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    with _lock:
        users = _load()
        if wallet in users:
            raise ValueError("This wallet is already registered — log in instead.")
        salt = secrets.token_bytes(16)
        users[wallet] = {
            "name": (name or "").strip()[:40],
            "salt": salt.hex(),
            "hash": _hash(password, salt),
            "created_at": time.time(),
        }
        _save(users)


def verify(wallet: str, password: str) -> bool:
    u = _load().get(wallet.strip())
    if not u:
        return False
    actual = _hash(password, bytes.fromhex(u["salt"]))
    return hmac.compare_digest(u["hash"], actual)


def exists(wallet: str) -> bool:
    return wallet.strip() in _load()


def get_name(wallet: str) -> str:
    return _load().get(wallet.strip(), {}).get("name", "")
