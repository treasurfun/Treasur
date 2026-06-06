"""Atomic file-based persistent storage.

Each launch is a JSON file under DATA_DIR/launches/<id>.json. Writes go to a
temp file then os.replace() for atomicity, so a crash mid-write can't corrupt
an existing record. A process-wide lock serialises writes within one worker.
"""
import json
import os
import threading
from typing import Optional

from cryptography.fernet import Fernet

from config import get_settings
from models import LaunchRecord

_settings = get_settings()
_lock = threading.RLock()
_LAUNCH_DIR = os.path.join(_settings.DATA_DIR, "launches")


def _ensure_dirs() -> None:
    os.makedirs(_LAUNCH_DIR, exist_ok=True)


def _fernet() -> Fernet:
    key = _settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_secret(secret_b58: str) -> str:
    return _fernet().encrypt(secret_b58.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def _path(launch_id: str) -> str:
    return os.path.join(_LAUNCH_DIR, f"{launch_id}.json")


def save_launch(record: LaunchRecord) -> None:
    _ensure_dirs()
    with _lock:
        tmp = _path(record.launch_id) + ".tmp"
        with open(tmp, "w") as f:
            f.write(record.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _path(record.launch_id))


def load_launch(launch_id: str) -> Optional[LaunchRecord]:
    p = _path(launch_id)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return LaunchRecord.model_validate_json(f.read())


def list_launches() -> list[LaunchRecord]:
    _ensure_dirs()
    out = []
    for name in os.listdir(_LAUNCH_DIR):
        if name.endswith(".json"):
            rec = load_launch(name[:-5])
            if rec:
                out.append(rec)
    return out


def find_by_mint(mint: str) -> Optional[LaunchRecord]:
    for rec in list_launches():
        if rec.mint == mint:
            return rec
    return None
