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
import base58
import httpx

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from config import get_settings
from models import TokenConfig
from services.solana_client import keypair_from_secret, client, get_balance_sol

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
    # Pinata's own CDN serves freshly-pinned content immediately; ipfs.io can
    # take minutes and time out, which makes PumpPortal's metadata fetch fail.
    return f"https://gateway.pinata.cloud/ipfs/{cid}"


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

    # Only include fields that have values — PumpPortal validates the fetched
    # metadata and rejects empty social URLs with a generic "Bad Request".
    metadata = {
        "name": cfg.name,
        "symbol": cfg.symbol,
        "image": image_url,
        "description": _build_description(cfg),
        "showName": True,
    }
    if cfg.twitter:
        metadata["twitter"] = cfg.twitter
    if cfg.telegram:
        metadata["telegram"] = cfg.telegram
    if cfg.website:
        metadata["website"] = cfg.website
    return _pinata_upload("metadata.json", json.dumps(metadata).encode(), "application/json")


def create_token(launch_secret: str, cfg: TokenConfig, dev_buy_sol: float) -> tuple[str, str]:
    """Create the token with a dev buy. Returns (mint_pubkey, signature)."""
    metadata_uri = _upload_metadata(cfg)
    print(f"[pumpfun] metadata uri: {metadata_uri}")

    # Make sure the metadata is actually served before creating (the API may
    # fetch the uri). Pinata's CDN serves it near-instantly; confirm anyway.
    for i in range(8):
        try:
            g = httpx.get(metadata_uri, timeout=15)
            if g.status_code == 200:
                print(f"[pumpfun] metadata reachable after {i + 1} check(s)")
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    else:
        print("[pumpfun] WARNING: metadata uri not confirmed reachable, sending anyway")

    launch_kp = keypair_from_secret(launch_secret)

    # PumpDev /api/create: we supply creator + metadata; it returns a base58
    # transaction (create + dev buy) and the generated mint's secret key. We
    # sign locally with creator + mint and broadcast via our own RPC.
    body = {
        "publicKey": str(launch_kp.pubkey()),
        "name": cfg.name,
        "symbol": cfg.symbol,
        "uri": metadata_uri,
        "buyAmountSol": dev_buy_sol,   # dev buy in SOL (0 = create only)
        "slippage": 30,
    }
    url = f"{_settings.PUMPDEV_API_URL}/api/create"
    r = httpx.post(url, json=body, timeout=90)
    if r.status_code != 200:
        try:
            payer_balance = get_balance_sol(body["publicKey"])
        except Exception as e:  # noqa: BLE001
            payer_balance = f"ERR {e}"
        diag = {
            "provider": "pumpdev",
            "status": r.status_code,
            "resp_body": (r.text or "")[:500],
            "uri": metadata_uri,
            "payer_balance_sol": payer_balance,
            "publicKey": body["publicKey"],
            "buyAmountSol": dev_buy_sol,
        }
        print(f"[pumpfun] pumpdev create failed: {json.dumps(diag)}")
        raise RuntimeError("Token create failed (pumpdev): " + json.dumps(diag))

    data = r.json()
    raw = base58.b58decode(data["transaction"])
    mint_kp = Keypair.from_base58_string(data["mintSecretKey"])
    mint = data.get("mint") or str(mint_kp.pubkey())

    # Sign with exactly the message's required signers, in their declared order
    # (works whether creator or mint is the fee payer).
    unsigned = VersionedTransaction.from_bytes(raw)
    msg = unsigned.message
    n = msg.header.num_required_signatures
    signer_pubkeys = list(msg.account_keys)[:n]
    kp_map = {launch_kp.pubkey(): launch_kp, mint_kp.pubkey(): mint_kp}
    try:
        ordered = [kp_map[pk] for pk in signer_pubkeys]
    except KeyError as e:  # a signer we don't hold — shouldn't happen for create
        raise RuntimeError(f"create tx needs unexpected signer {e}; signers={signer_pubkeys}")
    signed = VersionedTransaction(msg, ordered)

    c = client()
    sig = c.send_raw_transaction(
        bytes(signed),
        opts=TxOpts(skip_preflight=True, preflight_commitment=Confirmed),
    )
    return mint, str(sig.value)


def claim_creator_fees(launch_secret: str, mint: str | None = None) -> str:
    """Claim accumulated pump.fun creator fees to the launch wallet (via PumpDev)."""
    launch_kp = keypair_from_secret(launch_secret)
    body = {"publicKey": str(launch_kp.pubkey()), "priorityFee": 0.0001}
    if mint:
        body["mint"] = mint  # needed if fee-sharing is configured
    r = httpx.post(f"{_settings.PUMPDEV_API_URL}/api/claim-account", json=body, timeout=60)
    r.raise_for_status()
    unsigned = VersionedTransaction.from_bytes(r.content)
    signed = VersionedTransaction(unsigned.message, [launch_kp])
    c = client()
    sig = c.send_raw_transaction(
        bytes(signed), opts=TxOpts(skip_preflight=True, preflight_commitment=Confirmed)
    )
    return str(sig.value)
