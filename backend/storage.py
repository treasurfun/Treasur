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


# ── Competition state (single small JSON: last run + last winners) ──
_COMPETITION_FILE = os.path.join(_settings.DATA_DIR, "competition.json")


def load_competition() -> dict:
    """Last competition state: {last_run_ts, prize_sol, best_project, best_dev}."""
    try:
        with open(_COMPETITION_FILE, "r") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — missing/corrupt -> fresh state
        return {}


def save_competition(state: dict) -> None:
    with _lock:
        _ensure_dirs()
        tmp = _COMPETITION_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, _COMPETITION_FILE)


# --- automatic buyback-burn proof feed -------------------------------------
_BURNS_FILE = os.path.join(_settings.DATA_DIR, "burns.json")
_BURNS_CAP = 300


def load_burns() -> list:
    """All recorded automatic buyback-burn events (oldest first)."""
    try:
        with open(_BURNS_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — missing/corrupt -> empty
        return []


def append_burn(event: dict) -> None:
    """Append one burn event, keeping only the most recent _BURNS_CAP."""
    with _lock:
        _ensure_dirs()
        try:
            with open(_BURNS_FILE, "r") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception:  # noqa: BLE001
            data = []
        data.append(event)
        data = data[-_BURNS_CAP:]
        tmp = _BURNS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, _BURNS_FILE)


_DIST_FILE = os.path.join(_settings.DATA_DIR, "distributions.json")
_DIST_CAP = 400


def load_distributions() -> list:
    """All recorded asset-distribution events (oldest first)."""
    try:
        with open(_DIST_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — missing/corrupt -> empty
        return []


def append_distribution(event: dict) -> None:
    """Append one distribution event, keeping only the most recent _DIST_CAP."""
    with _lock:
        _ensure_dirs()
        try:
            with open(_DIST_FILE, "r") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception:  # noqa: BLE001
            data = []
        data.append(event)
        data = data[-_DIST_CAP:]
        tmp = _DIST_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, _DIST_FILE)
