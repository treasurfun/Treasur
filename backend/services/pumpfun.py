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
    """Upload a file to Pinata and return its public ipfs.io gateway URL."""
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
    """User description + the auto branding line shown on the coin page,
    e.g. 'Made with voult.fun - All fees are swapped to HYPE and distributed to holders.'"""
    assets = ", ".join(a.upper() for a in cfg.payout_assets) or "real assets"
    branding = (
        f"Made with {_settings.SITE_NAME} - All fees are swapped to {assets} "
        f"and distributed to holders."
    )
    user_desc = (cfg.description or "").strip()
    return f"{user_desc}\n\n{branding}" if user_desc else branding


def _upload_metadata(cfg: TokenConfig) -> str:
    """Pin image + JSON metadata to IPFS (Pinata), return the metadata URI."""
    image_url = ""
    if cfg.image_url:
        img = httpx.get(cfg.image_url, timeout=30).content
        image_url = _pinata_upload("image.png", img, "image/png")

    metadata = {
        "name": cfg.name,
        "symbol": cfg.symbol,
        "description": _build_description(cfg),
        "image": image_url,
        "twitter": cfg.twitter or "",
        "telegram": cfg.telegram or "",
        "website": cfg.website or "",
        "showName": True,
    }
    return _pinata_upload("metadata.json", json.dumps(metadata).encode(), "application/json")


def create_token(launch_secret: str, cfg: TokenConfig, dev_buy_sol: float) -> tuple[str, str]:
    """Create the token with a dev buy. Returns (mint_pubkey, signature)."""
    metadata_uri = _upload_metadata(cfg)

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
    r = httpx.post(_settings.PUMPPORTAL_TRADE_URL, json=body, timeout=60)
    r.raise_for_status()

    # create must be signed by BOTH the mint authority and the payer (mint first)
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
