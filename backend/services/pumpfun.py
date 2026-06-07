"""PumpFun token creation and creator-fee claiming (via PumpPortal local API).

Verified against PumpPortal docs (pumpportal.fun/creation and /creator-fee):
  * /api/trade-local returns an UNSIGNED serialized tx that we sign locally,
    so the private key never leaves this backend.
  * pump.fun's old /api/ipfs metadata endpoint is DEPRECATED. Metadata must now
    be pinned to a third-party IPFS service; we use Pinata (needs PINATA_JWT).
  * "create" must be signed by BOTH the mint keypair and the payer.
  * "collectCreatorFee" claims all pump.fun creator fees at once (no mint needed)
    and is signed by the payer only.
"""
import json
import time
import httpx

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from config import get_settings
from models import TokenConfig
from services.solana_client import keypair_from_secret, client

_settings = get_settings()

PINATA_UPLOAD_URL = "https://uploads.pinata.cloud/v3/files"


def _pinata_upload(filename: str, content: bytes, content_type: str) -> str:
    """Upload a file to Pinata and return its gateway URL (served immediately)."""
    if not _settings.PINATA_JWT:
        raise RuntimeError("PINATA_JWT is not set — required to pin token metadata.")
    r = httpx.post(
        PINATA_UPLOAD_URL,
        headers={"Authorization": f"Bearer {_settings.PINATA_JWT}"},
        data={"network": "public"},
        files={"file": (filename, content, content_type)},
        timeout=60,
    )
    r.raise_for_status()
    cid = r.json()["data"]["cid"]
    return f"https://ipfs.io/ipfs/{cid}"


def _build_description(cfg: TokenConfig) -> str:
    """User description + auto branding line shown on the coin page."""
    assets = ", ".join(a.upper() for a in cfg.payout_assets) or "real assets"
    branding = (
        f"This token was created with {_settings.SITE_NAME} and backed by {assets}. "
        f"All creator fees are swapped to {assets} and distributed to holders."
    )
    user_desc = (cfg.description or "").strip()
    return f"{user_desc}\n\n{branding}" if user_desc else branding


def _decode_data_url(data_url: str) -> tuple[bytes, str, str]:
    """Decode a base64 data URL -> (bytes, content_type, filename)."""
    import base64 as _b64
    ext = "png"
    content_type = "image/png"
    payload = data_url
    if data_url.startswith("data:"):
        header, payload = data_url.split(",", 1)
        # header like: data:image/jpeg;base64
        if ":" in header and ";" in header:
            content_type = header.split(":", 1)[1].split(";", 1)[0] or content_type
        ext = content_type.split("/")[-1] or "png"
    return _b64.b64decode(payload), content_type, f"image.{ext}"


def _upload_metadata(cfg: TokenConfig) -> str:
    """Pin image + JSON metadata to IPFS (Pinata), return the metadata URI."""
    image_url = ""
    if cfg.image_data:  # uploaded / drag-dropped file (base64 data URL)
        content, ctype, fname = _decode_data_url(cfg.image_data)
        image_url = _pinata_upload(fname, content, ctype)
    elif cfg.image_url:  # fallback: fetch from a URL
        img = httpx.get(cfg.image_url, timeout=30).content
        image_url = _pinata_upload("image.png", img, "image/png")

    if not image_url:
        raise RuntimeError("A token image is required — please upload one before launching.")

    # field order/shape mirrors the official PumpPortal creation example
    metadata = {
        "name": cfg.name,
        "symbol": cfg.symbol,
        "image": image_url,
        "description": _build_description(cfg),
        "twitter": cfg.twitter or "",
        "telegram": cfg.telegram or "",
        "website": cfg.website or "",
        "showName": True,
    }
    return _pinata_upload("metadata.json", json.dumps(metadata).encode(), "application/json")


def create_token(launch_secret: str, cfg: TokenConfig, dev_buy_sol: float) -> tuple[str, str]:
    """Create the token with a dev buy. Returns (mint_pubkey, signature)."""
    metadata_uri = _upload_metadata(cfg)
    print(f"[pumpfun] metadata uri: {metadata_uri}")

    launch_kp = keypair_from_secret(launch_secret)
    mint_kp = Keypair()  # the new token mint

    body = {
        "publicKey": str(launch_kp.pubkey()),
        "action": "create",
        "tokenMetadata": {
            "name": cfg.name,
            "symbol": cfg.symbol,
            "uri": metadata_uri,
        },
        "mint": str(mint_kp.pubkey()),
        "denominatedInSol": "true",
        "amount": dev_buy_sol,          # dev buy in SOL
        "slippage": 10,
        "priorityFee": 0.0005,
        "pool": "pump",
    }
    # PumpPortal can 400 transiently while the freshly-pinned IPFS metadata
    # propagates (its server reads the uri), so wait briefly then retry.
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, */*",
    }
    time.sleep(3)
    r = None
    last_err = ""
    for attempt in range(4):
        r = httpx.post(_settings.PUMPPORTAL_TRADE_URL, json=body, headers=headers, timeout=60)
        if r.status_code == 200:
            break
        last_err = (r.text or "")[:800]
        print(f"[pumpfun] create attempt {attempt + 1}/4 -> {r.status_code}; body={last_err!r}; uri={metadata_uri}")
        time.sleep(4 * (attempt + 1))
    if r is None or r.status_code != 200:
        uri_check = ""
        try:
            g = httpx.get(metadata_uri, timeout=15)
            uri_check = f"{g.status_code} {g.headers.get('content-type', '')}"
        except Exception as e:  # noqa: BLE001
            uri_check = f"ERR {e}"
        diag = {
            "status": r.status_code if r else None,
            "server": r.headers.get("server") if r else None,
            "cf_ray": r.headers.get("cf-ray") if r else None,
            "ctype": r.headers.get("content-type") if r else None,
            "resp_body": (r.text or "")[:500] if r else None,
            "uri": metadata_uri,
            "uri_get": uri_check,
            "sent": {k: body.get(k) for k in ("action", "denominatedInSol", "amount", "slippage", "priorityFee", "pool")},
            "tokenMetadata": body.get("tokenMetadata"),
            "publicKey": body.get("publicKey"),
            "mint": body.get("mint"),
        }
        raise RuntimeError("PumpPortal create failed: " + json.dumps(diag))
    unsigned = VersionedTransaction.from_bytes(r.content)
    signed = VersionedTransaction(unsigned.message, [mint_kp, launch_kp])

    c = client()
    sig = c.send_raw_transaction(
        bytes(signed),
        opts=TxOpts(skip_preflight=True, preflight_commitment=Confirmed),
    )
    return str(mint_kp.pubkey()), str(sig.value)


def claim_creator_fees(launch_secret: str) -> str:
    """Claim all accumulated pump.fun creator fees to the launch wallet."""
    launch_kp = keypair_from_secret(launch_secret)
    body = {
        "publicKey": str(launch_kp.pubkey()),
        "action": "collectCreatorFee",
        "priorityFee": 0.0005,
        "pool": "pump",
    }
    r = httpx.post(_settings.PUMPPORTAL_TRADE_URL, json=body, timeout=60)
    r.raise_for_status()
    unsigned = VersionedTransaction.from_bytes(r.content)
    signed = VersionedTransaction(unsigned.message, [launch_kp])
    c = client()
    sig = c.send_raw_transaction(
        bytes(signed), opts=TxOpts(skip_preflight=True, preflight_commitment=Confirmed)
    )
    return str(sig.value)
