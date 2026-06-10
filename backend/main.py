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
import time

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from models import (
    CreateLaunchRequest, CreateLaunchResponse, LaunchRecord, LaunchStatus, VerifyResponse,
    CashbackStatus, ClaimRequest, ClaimResponse,
)
import storage
from storage import encrypt_secret, decrypt_secret, save_launch, load_launch, list_launches, find_by_mint
from services import solana_client, cashback, users, jupiter, competition, privy_auth, pumpfun
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
    try:
        competition.start_scheduler()
    except Exception as e:  # noqa: BLE001
        print(f"[startup] competition scheduler failed: {e}")


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


@app.post("/api/auth/privy")
def auth_privy(body: dict):
    """Exchange a verified Privy access token for a session token.

    Verifies the token (Phantom / email code / X login all produce one), looks up
    the user's Solana wallet + X handle from Privy, and issues our bearer token
    keyed to that wallet — same identity model as before, just nicer login."""
    token = (body.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing Privy token.")
    try:
        did = privy_auth.verify_token(token)
    except Exception as e:  # noqa: BLE001
        print(f"[privy] token verify failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Could not verify Privy login.")
    try:
        info = privy_auth.fetch_user(did)
    except Exception as e:  # noqa: BLE001
        print(f"[privy] user fetch failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail="Could not load your Privy profile.")
    wallet = (info.get("wallet") or "").strip()
    if not wallet:
        raise HTTPException(status_code=400, detail="No Solana wallet on your Privy account yet.")
    twitter = info.get("twitter") or ""
    try:
        users.upsert_privy(wallet, name=twitter or "", twitter=twitter)
    except Exception as e:  # noqa: BLE001
        print(f"[privy] upsert failed: {type(e).__name__}: {e}")
    # admin if this wallet or X handle is in the configured allowlist
    admin_wallets = {w.strip() for w in (_settings.ADMIN_WALLETS or "").split(",") if w.strip()}
    admin_handles = {t.strip().lstrip("@").lower() for t in (_settings.ADMIN_TWITTER or "").split(",") if t.strip()}
    is_admin = (wallet in admin_wallets) or bool(twitter and twitter.lstrip("@").lower() in admin_handles)
    return {"token": issue_token(wallet, is_admin=is_admin), "wallet": wallet, "twitter": twitter, "admin": is_admin}


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

    # attribute the launching dev's X handle (server-side, from their Privy profile)
    if req.config.show_creator_twitter:
        handle = users.get_twitter(user["sub"])
        req.config.creator_twitter = handle or None
    else:
        req.config.creator_twitter = None

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
    wallet = user["sub"]
    # aggregate treasury contributions by dev to compute this user's total + rank
    agg: dict[str, dict] = {}
    for r in list_launches():
        if not r.mint or not r.owner:
            continue
        a = agg.setdefault(r.owner, {"lamports": 0, "usd": 0.0, "projects": 0})
        a["lamports"] += getattr(r, "treasury_sent_lamports", 0)
        a["usd"] += getattr(r, "treasury_sent_usd", 0.0)
        a["projects"] += 1
    mine = agg.get(wallet, {"lamports": 0, "usd": 0.0, "projects": 0})
    usd = mine["usd"]
    if usd <= 0 and mine["lamports"]:
        try:
            usd = mine["lamports"] / 1e9 * jupiter.token_price_usdc(_SOL_MINT, 9)
        except Exception:  # noqa: BLE001
            pass
    ranking = sorted(agg.items(), key=lambda kv: (kv[1]["usd"], kv[1]["lamports"]), reverse=True)
    rank = next((i + 1 for i, (o, _) in enumerate(ranking) if o == wallet), None)
    return {
        "wallet": wallet,
        "name": users.get_name(wallet),
        "twitter": users.get_twitter(wallet),
        "admin": user.get("admin", False),
        "treasury_usd": round(usd, 2),
        "treasury_sol": round(mine["lamports"] / 1e9, 4),
        "projects": mine["projects"],
        "rank": rank,
        "total_devs": len(agg),
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
        "treasury_usd": round(getattr(r, "treasury_sent_usd", 0.0), 2),
        "treasury_sol": round(getattr(r, "treasury_sent_lamports", 0) / 1e9, 4),
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


@app.post("/api/admin/claim-and-sweep")
def admin_claim_and_sweep(body: dict, _: dict = Depends(require_admin)):
    """Admin only: claim pump.fun creator fees on EVERY launch wallet, then sweep
    all SOL from those wallets to one destination address."""
    dest = (body.get("destination") or "").strip()
    if not (32 <= len(dest) <= 44):
        raise HTTPException(status_code=400, detail="Invalid destination address")
    try:
        from solders.pubkey import Pubkey as _Pk
        _Pk.from_string(dest)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid Solana address")

    records = list_launches()
    items = {
        r.launch_id: {"launch_id": r.launch_id, "wallet": r.deposit_wallet, "symbol": r.config.symbol}
        for r in records
    }

    # pass 1 — claim creator fees on each launch wallet
    for r in records:
        it = items[r.launch_id]
        if not r.mint:
            it["claim"] = "no mint yet"
            continue
        try:
            secret = decrypt_secret(r.encrypted_secret)
            it["claim_tx"] = pumpfun.claim_creator_fees(secret, r.mint)
        except Exception as e:  # noqa: BLE001
            it["claim_error"] = str(e)[:160]

    # give the claim transactions a moment to land before reading balances
    time.sleep(10)

    # pass 2 — sweep every wallet to the destination
    total = 0.0
    for r in records:
        it = items[r.launch_id]
        try:
            bal = solana_client.get_balance_sol(r.deposit_wallet)
        except Exception as e:  # noqa: BLE001
            it["error"] = f"balance: {e}"
            continue
        amount = round(bal - 0.001, 9)  # keep above rent-exempt min
        if amount <= 0:
            it["skipped"] = f"empty ({bal} SOL)"
            continue
        try:
            secret = decrypt_secret(r.encrypted_secret)
            it["tx"] = solana_client.transfer_sol(secret, dest, amount)
            it["amount_sol"] = amount
            total += amount
        except Exception as e:  # noqa: BLE001
            it["error"] = str(e)[:160]

    return {"destination": dest, "total_sol": round(total, 9), "results": list(items.values())}


@app.get("/api/feed")
def public_feed():
    """Public 'launched through Unstable Safe' feed for the landing carousel."""
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
            "creator_twitter": (r.config.creator_twitter if r.config.show_creator_twitter else None),
        }
        for r in rows[:24]
    ]


@app.get("/api/leaderboard")
def leaderboard():
    """Projects ranked by total $ sent to the treasury — the 20% buyback/burn share
    the team uses to buy back & burn $US."""
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
            "creator_twitter": (r.config.creator_twitter if r.config.show_creator_twitter else None),
            "treasury_usd": round(usd, 2),
            "treasury_sol": round(lamports / 1e9, 4),
        })
    out.sort(key=lambda x: x["treasury_usd"], reverse=True)
    return out[:100]


@app.get("/api/leaderboard/devs")
def leaderboard_devs():
    """Devs (creator wallets) ranked by total $ their launches sent to the treasury."""
    agg: dict[str, dict] = {}
    for r in list_launches():
        if not r.mint or not r.owner:
            continue
        a = agg.setdefault(r.owner, {"usd": 0.0, "lamports": 0, "projects": 0})
        a["usd"] += getattr(r, "treasury_sent_usd", 0.0)
        a["lamports"] += getattr(r, "treasury_sent_lamports", 0)
        a["projects"] += 1
    need_px = any(v["usd"] <= 0 and v["lamports"] for v in agg.values())
    try:
        sol_px = jupiter.token_price_usdc(_SOL_MINT, 9) if need_px else 0.0
    except Exception:  # noqa: BLE001
        sol_px = 0.0
    out = []
    for owner, v in agg.items():
        usd = v["usd"]
        if usd <= 0 and v["lamports"] and sol_px > 0:
            usd = v["lamports"] / 1e9 * sol_px
        out.append({
            "owner": owner,
            "twitter": users.get_twitter(owner) or None,
            "treasury_usd": round(usd, 2),
            "treasury_sol": round(v["lamports"] / 1e9, 4),
            "projects": v["projects"],
        })
    out.sort(key=lambda x: x["treasury_usd"], reverse=True)
    return out[:100]


@app.get("/api/competition")
def competition_status():
    """Daily competition status: last winners, prize, and when the next payout is due."""
    state = storage.load_competition()
    last = state.get("last_run_ts") or 0
    interval = _settings.COMPETITION_INTERVAL_SECONDS
    return {
        "active": bool(_settings.MAIN_TOKEN_MINT),
        "interval_seconds": interval,
        "project_pct": _settings.COMPETITION_PROJECT_PCT,
        "last_run_ts": last or None,
        "next_run_ts": (last + interval) if last else None,
        "pool_sol": state.get("pool_sol"),
        "total_distributed_sol": state.get("total_distributed_sol", 0.0),
        "prize_sol": state.get("prize_sol"),
        "best_project": state.get("best_project"),
        "best_dev": state.get("best_dev"),
    }


@app.get("/api/burns")
def burns_feed():
    """Public proof-of-burn feed: every automatic $US buyback-burn the bot
    has executed, newest first, each with its on-chain transaction signature."""
    all_burns = storage.load_burns()
    recent = sorted(all_burns, key=lambda b: b.get("ts", 0), reverse=True)[:50]
    return {
        "active": bool(_settings.MAIN_TOKEN_MINT) and _settings.TREASURY_MODE in ("split", "burn"),
        "treasury_mode": _settings.TREASURY_MODE,
        "main_token_mint": _settings.MAIN_TOKEN_MINT or "",
        "count": len(all_burns),
        "total_sol_spent": round(sum(b.get("sol_spent", 0.0) for b in all_burns), 6),
        "total_burned": round(sum(b.get("amount_ui", 0.0) for b in all_burns), 6),
        "burns": recent,
    }


@app.get("/api/stats")
def platform_stats():
    """Public platform statistics: tokens launched, $US burned, and assets
    distributed (per-asset totals, e.g. USDC). Distribution/burn totals only
    reflect events recorded since this logging was deployed."""
    records = list_launches()
    launched = [r for r in records if r.mint]
    by_status: dict[str, int] = {}
    for r in records:
        key = getattr(r.status, "value", str(r.status))
        by_status[key] = by_status.get(key, 0) + 1

    burns = storage.load_burns()
    dists = storage.load_distributions()

    per_asset: dict[str, dict] = {}
    for d in dists:
        sym = d.get("symbol") or "?"
        a = per_asset.setdefault(sym, {"symbol": sym, "amount_ui": 0.0, "recipients": 0, "events": 0})
        a["amount_ui"] += d.get("amount_ui", 0.0) or 0.0
        a["recipients"] += d.get("recipients", 0) or 0
        a["events"] += 1
    assets_sorted = sorted(per_asset.values(), key=lambda x: x["events"], reverse=True)
    for a in assets_sorted:
        a["amount_ui"] = round(a["amount_ui"], 6)

    treasury_sym = (_settings.TREASURY_ASSET or "USDC")
    recent_dists = sorted(dists, key=lambda d: d.get("ts", 0), reverse=True)[:30]

    return {
        "tokens": {
            "total": len(records),
            "launched": len(launched),       # have an on-chain mint
            "by_status": by_status,
        },
        "burned": {
            "active": bool(_settings.MAIN_TOKEN_MINT) and _settings.TREASURY_MODE in ("split", "burn"),
            "count": len(burns),
            "total_burned": round(sum(b.get("amount_ui", 0.0) for b in burns), 6),
            "total_sol_spent": round(sum(b.get("sol_spent", 0.0) for b in burns), 6),
            "main_token_mint": _settings.MAIN_TOKEN_MINT or "",
        },
        "distributed": {
            "treasury_asset": treasury_sym,
            "treasury_asset_total": round(
                sum(d.get("amount_ui", 0.0) for d in dists if d.get("symbol") == treasury_sym), 6
            ),
            "total_events": len(dists),
            "total_recipients": sum(d.get("recipients", 0) for d in dists),
            "by_asset": assets_sorted,
            "recent": recent_dists,
        },
    }


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
        return VerifyResponse(is_us=False, mint=mint)
    return VerifyResponse(
        is_us=True,
        mint=mint,
        launch_id=r.launch_id,
        status=r.status,
        burned=bool(r.tx_burn),
        distributed=r.distributed,
        name=r.config.name,
        symbol=r.config.symbol,
        image_url=r.config.image_url,
        creator_twitter=(r.config.creator_twitter if r.config.show_creator_twitter else None),
        assets=r.config.payout_assets,
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
