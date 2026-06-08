"""VOULT backend — FastAPI app.

Endpoints:
  POST /api/auth/login        -> issue a user (or admin) bearer token
  POST /api/launches          -> create a launch config + fresh deposit wallet
  POST /api/launches/{id}/start -> begin the lifecycle once the wallet is funded
  GET  /api/launches/{id}     -> poll status/progress
  GET  /api/launches          -> (owner) list own launches
  GET  /api/verify/{mint}     -> public: was this token launched via VOULT?
  GET  /api/admin/launches    -> (admin) list everything
  GET  /api/assets            -> supported payout assets
"""
import secrets as _secrets

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from models import (
    CreateLaunchRequest, CreateLaunchResponse, LaunchRecord, LaunchStatus, VerifyResponse,
    CashbackStatus, ClaimRequest, ClaimResponse,
)
import storage
from storage import encrypt_secret, decrypt_secret, save_launch, load_launch, list_launches, find_by_mint
from services import solana_client, cashback, users, jupiter
from orchestrator import start_launch, resume_pending
from auth import issue_token, current_user, require_admin
from assets import ASSETS, all_symbols

_settings = get_settings()
_SOL_MINT = "So11111111111111111111111111111111111111112"  # wrapped SOL, for USD price
app = FastAPI(title="VOULT", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _resume_on_startup():
    try:
        import os as _os
        from config import get_settings as _gs
        data_dir = _gs().DATA_DIR
        count = len(list_launches())
        mounted = _os.path.ismount(data_dir)
        flag = "VOLUME MOUNTED — data persists across redeploys" if mounted \
            else "NOT A VOLUME — data is EPHEMERAL and will be wiped on redeploy"
        print(f"[startup] DATA_DIR={data_dir} — {count} launch record(s) found — [{flag}]")
    except Exception as e:  # noqa: BLE001
        print(f"[startup] could not count launches: {e}")
    try:
        resume_pending()
    except Exception as e:  # noqa: BLE001
        print(f"[startup] resume_pending failed: {e}")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/assets")
def get_assets():
    return ASSETS


@app.post("/api/auth/register")
def register(body: dict):
    """Quick register: name + Solana wallet + password. Stores a hashed password."""
    name = body.get("name", "")
    wallet = body.get("wallet", "").strip()
    password = body.get("password", "")
    try:
        users.register(name, wallet, password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": issue_token(wallet, is_admin=False), "name": users.get_name(wallet)}


@app.post("/api/auth/login")
def login(body: dict):
    """Verified login. Admin if password == ADMIN_PASSWORD."""
    wallet = body.get("wallet", "").strip()
    password = body.get("password", "")
    if _settings.ADMIN_PASSWORD and password == _settings.ADMIN_PASSWORD:
        return {"token": issue_token(wallet or "admin", is_admin=True), "name": "admin"}
    if not users.verify(wallet, password):
        raise HTTPException(status_code=401, detail="Wrong wallet or password.")
    return {"token": issue_token(wallet, is_admin=False), "name": users.get_name(wallet)}


@app.post("/api/launches", response_model=CreateLaunchResponse)
def create_launch(req: CreateLaunchRequest, user: dict = Depends(current_user)):
    bad = [s for s in req.config.payout_assets if s.upper() not in all_symbols()]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown assets: {bad}")
    if not (1 <= len(req.config.payout_assets) <= 3):
        raise HTTPException(status_code=400, detail="Pick between 1 and 3 assets.")
    w = req.config.payout_weights
    if w:
        if set(w.keys()) != set(req.config.payout_assets):
            raise HTTPException(status_code=400, detail="Weights must match selected assets.")
        if abs(sum(w.values()) - 100) > 0.5:
            raise HTTPException(status_code=400, detail="Weights must sum to 100.")

    pubkey, secret_b58 = solana_client.new_wallet()
    launch_id = _secrets.token_urlsafe(9)
    required = _settings.MIN_FUNDING_SOL  # deploy cost + dev buy (no platform fee)

    record = LaunchRecord(
        launch_id=launch_id,
        owner=user["sub"],
        config=req.config,
        deposit_wallet=pubkey,
        encrypted_secret=encrypt_secret(secret_b58),
        status=LaunchStatus.CREATED,
    )
    save_launch(record)
    return CreateLaunchResponse(
        launch_id=launch_id,
        deposit_wallet=pubkey,
        required_sol=required,
        status=record.status,
    )


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {
        "wallet": user["sub"],
        "name": users.get_name(user["sub"]),
        "admin": user.get("admin", False),
    }


@app.post("/api/launches/{launch_id}/start")
def start(launch_id: str, user: dict = Depends(current_user)):
    record = load_launch(launch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if record.owner != user["sub"] and not user.get("admin"):
        raise HTTPException(status_code=403, detail="Not your launch")
    if record.status not in (LaunchStatus.CREATED, LaunchStatus.FUNDED):
        raise HTTPException(status_code=409, detail=f"Already {record.status}")

    bal = solana_client.get_balance_sol(record.deposit_wallet)
    if bal < _settings.MIN_FUNDING_SOL - 0.001:
        raise HTTPException(status_code=402, detail=f"Underfunded: {bal} SOL (need {_settings.MIN_FUNDING_SOL})")

    record.status = LaunchStatus.FUNDED
    save_launch(record)
    start_launch(record)
    return {"status": "started", "launch_id": launch_id}


def _public_view(r: LaunchRecord) -> dict:
    return {
        "launch_id": r.launch_id,
        "status": r.status,
        "config": r.config.model_dump(),
        "deposit_wallet": r.deposit_wallet,
        "mint": r.mint,
        "tx_create": r.tx_create,
        "tx_burn": r.tx_burn,
        "cycles_done": r.cycles_done,
        "distributed": r.distributed,
        "fees_claimed_sol": r.fees_claimed_sol,
        "log": r.log,
        "error": r.error,
    }


@app.get("/api/launches/{launch_id}/balance")
def launch_balance(launch_id: str, user: dict = Depends(current_user)):
    record = load_launch(launch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if record.owner != user["sub"] and not user.get("admin"):
        raise HTTPException(status_code=403, detail="Not your launch")
    try:
        bal = solana_client.get_balance_sol(record.deposit_wallet)
    except Exception:  # noqa: BLE001
        bal = 0.0
    req = _settings.MIN_FUNDING_SOL
    return {"balance_sol": bal, "required_sol": req, "funded": bal >= req - 0.001}


@app.post("/api/launches/{launch_id}/withdraw")
def launch_withdraw(launch_id: str, body: dict, user: dict = Depends(current_user)):
    """Send the launch wallet's SOL to a destination the owner controls
    (recover funds from a launch that failed / never started)."""
    record = load_launch(launch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if record.owner != user["sub"] and not user.get("admin"):
        raise HTTPException(status_code=403, detail="Not your launch")
    dest = (body.get("destination") or "").strip()
    if not (32 <= len(dest) <= 44):
        raise HTTPException(status_code=400, detail="Invalid destination address")
    try:
        from solders.pubkey import Pubkey as _Pk
        _Pk.from_string(dest)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid Solana address")
    try:
        bal = solana_client.get_balance_sol(record.deposit_wallet)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not read balance: {e}")
    amount = round(bal - 0.001, 9)  # keep above rent-exempt min so the tx isn't rejected
    if amount <= 0:
        raise HTTPException(status_code=400, detail=f"Nothing to withdraw (balance {bal} SOL)")
    try:
        secret = decrypt_secret(record.encrypted_secret)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not decrypt wallet key (ENCRYPTION_KEY changed?): {e}")
    try:
        sig = solana_client.transfer_sol(secret, dest, amount)
    except Exception as e:  # noqa: BLE001 — surface the real chain error to the user
        raise HTTPException(status_code=502, detail=f"Transfer failed: {e}")
    return {"tx": sig, "amount_sol": amount, "destination": dest, "from": record.deposit_wallet}


@app.post("/api/withdraw-all")
def withdraw_all(body: dict, user: dict = Depends(current_user)):
    """Drain SOL from ALL of the caller's launch wallets to one destination."""
    dest = (body.get("destination") or "").strip()
    if not (32 <= len(dest) <= 44):
        raise HTTPException(status_code=400, detail="Invalid destination address")
    try:
        from solders.pubkey import Pubkey as _Pk
        _Pk.from_string(dest)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid Solana address")

    results = []
    total = 0.0
    for record in list_launches():
        if record.owner != user["sub"] and not user.get("admin"):
            continue
        item = {"launch_id": record.launch_id, "wallet": record.deposit_wallet, "symbol": record.config.symbol}
        try:
            bal = solana_client.get_balance_sol(record.deposit_wallet)
        except Exception as e:  # noqa: BLE001
            item["error"] = f"balance: {e}"
            results.append(item)
            continue
        amount = round(bal - 0.001, 9)  # keep above rent-exempt min
        if amount <= 0:
            item["skipped"] = f"empty ({bal} SOL)"
            results.append(item)
            continue
        try:
            secret = decrypt_secret(record.encrypted_secret)
            sig = solana_client.transfer_sol(secret, dest, amount)
            item["amount_sol"] = amount
            item["tx"] = sig
            total += amount
        except Exception as e:  # noqa: BLE001
            item["error"] = str(e)[:200]
        results.append(item)
    return {"destination": dest, "total_sol": round(total, 9), "results": results}


@app.get("/api/feed")
def public_feed():
    """Public 'launched through Treasur' feed for the landing carousel."""
    rows = [r for r in list_launches() if r.mint]
    rows.sort(key=lambda r: getattr(r, "created_at", 0), reverse=True)
    return [
        {
            "launch_id": r.launch_id,
            "name": r.config.name,
            "symbol": r.config.symbol,
            "mint": r.mint,
            "image_url": r.config.image_url,
            "assets": r.config.payout_assets,
            "status": r.status,
        }
        for r in rows[:24]
    ]


@app.get("/api/leaderboard")
def leaderboard():
    """Projects ranked by total $ sent to the treasury — the 20% buyback/burn share
    the team uses to buy back & burn $TREASUR."""
    rows = [r for r in list_launches() if r.mint]
    # only hit the price API if some record has raw SOL but no captured USD
    need_px = any(
        (getattr(r, "treasury_sent_usd", 0.0) <= 0) and getattr(r, "treasury_sent_lamports", 0)
        for r in rows
    )
    try:
        sol_px = jupiter.token_price_usdc(_SOL_MINT, 9) if need_px else 0.0
    except Exception:  # noqa: BLE001
        sol_px = 0.0
    out = []
    for r in rows:
        lamports = getattr(r, "treasury_sent_lamports", 0)
        usd = getattr(r, "treasury_sent_usd", 0.0)
        if usd <= 0 and lamports and sol_px > 0:
            usd = lamports / 1e9 * sol_px
        out.append({
            "launch_id": r.launch_id,
            "name": r.config.name,
            "symbol": r.config.symbol,
            "mint": r.mint,
            "image_url": r.config.image_url,
            "twitter": r.config.twitter,
            "treasury_usd": round(usd, 2),
            "treasury_sol": round(lamports / 1e9, 4),
        })
    out.sort(key=lambda x: x["treasury_usd"], reverse=True)
    return out[:100]


@app.get("/api/launches/{launch_id}")
def get_launch(launch_id: str, user: dict = Depends(current_user)):
    record = load_launch(launch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if record.owner != user["sub"] and not user.get("admin"):
        raise HTTPException(status_code=403, detail="Not your launch")
    return _public_view(record)


@app.get("/api/launches")
def my_launches(user: dict = Depends(current_user)):
    return [_public_view(r) for r in list_launches() if r.owner == user["sub"] or user.get("admin")]


@app.get("/api/verify/{mint}", response_model=VerifyResponse)
def verify(mint: str):
    r = find_by_mint(mint)
    if not r:
        return VerifyResponse(is_treasur=False, mint=mint)
    return VerifyResponse(
        is_treasur=True,
        mint=mint,
        launch_id=r.launch_id,
        status=r.status,
        burned=bool(r.tx_burn),
        distributed=r.distributed,
    )


@app.get("/api/launches/{launch_id}/cashback", response_model=CashbackStatus)
def cashback_status(launch_id: str, user: dict = Depends(current_user)):
    record = load_launch(launch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    return cashback.status(record, user["sub"])


@app.post("/api/launches/{launch_id}/claim", response_model=ClaimResponse)
def claim_cashback(launch_id: str, body: ClaimRequest, user: dict = Depends(current_user)):
    record = load_launch(launch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if body.asset.upper() not in all_symbols():
        raise HTTPException(status_code=400, detail="Unknown asset")
    try:
        tx, sol = cashback.claim(record, user["sub"], body.asset)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ClaimResponse(tx=tx, asset=body.asset.upper(), sol_spent=sol)


@app.get("/api/admin/launches")
def admin_launches(_: dict = Depends(require_admin)):
    return [_public_view(r) for r in list_launches()]
