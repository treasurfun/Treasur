"""Launch orchestrator.

Drives the full lifecycle for one launch on a background thread:
  fund-check -> create token (dev buy) -> burn dev tokens -> swap SOL to assets
  -> N distribution cycles { fetch holders, distribute, claim fees, reinvest }.

A semaphore caps the number of simultaneous launches (default 20). State is
persisted after every transition so a restart can be reasoned about manually.
"""
import threading
import time
import traceback

from config import get_settings
from models import LaunchRecord, LaunchStatus
from storage import save_launch, decrypt_secret, list_launches, append_burn, append_distribution
from assets import resolve_mint
from services import solana_client, pumpfun, jupiter, helius, distribution, cashback
from solders.pubkey import Pubkey as _Pubkey

_settings = get_settings()
_PUMP_FUN_PROGRAM = _Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
_semaphore = threading.Semaphore(_settings.MAX_CONCURRENT_LAUNCHES)
LAMPORTS_PER_SOL = 1_000_000_000
_SOL_MINT = "So11111111111111111111111111111111111111112"  # wrapped SOL, for USD price


def _set(record: LaunchRecord, status: LaunchStatus) -> None:
    record.status = status
    save_launch(record)


# ordered lifecycle, used to skip phases already done when resuming after a restart
_RANK = {
    LaunchStatus.CREATED: 0,
    LaunchStatus.FUNDED: 1,
    LaunchStatus.TOKEN_CREATED: 2,
    LaunchStatus.BURNED: 3,
    LaunchStatus.SWAPPED: 4,
    LaunchStatus.DISTRIBUTING: 5,
    LaunchStatus.COMPLETE: 6,
    LaunchStatus.FAILED: 99,
}


def _reached(record: LaunchRecord, status: LaunchStatus) -> bool:
    return _RANK.get(record.status, 0) >= _RANK[status]


def _log(record: LaunchRecord, msg: str) -> None:
    record.log.append(msg)
    if len(record.log) > 400:
        record.log = record.log[-400:]
    save_launch(record)


def _alloc(total_lamports: int, assets: list[str], weights: dict) -> dict[str, int]:
    """Split a lamport budget across assets by weight (equal if none given)."""
    if not assets:
        return {}
    if weights:
        return {s: int(total_lamports * weights.get(s, 0) / 100) for s in assets}
    per = total_lamports // len(assets)
    return {s: per for s in assets}


def _run(record: LaunchRecord) -> None:
    secret = decrypt_secret(record.encrypted_secret)
    cfg = record.config
    assets = [a for a in cfg.payout_assets] or []

    # 1. create token with dev buy (skip if already created — resume-safe)
    if not record.mint:
        _log(record, "Building tx for token...")
        mint, tx, image_url = pumpfun.create_token(secret, cfg, _settings.DEV_BUY_SOL)
        record.mint = mint
        record.tx_create = tx
        if image_url:
            record.config.image_url = image_url  # so the homepage feed shows the dev's image
        _set(record, LaunchStatus.TOKEN_CREATED)
        _log(record, f"Created: {mint}")
        _log(record, "[waiting] Waiting 8s for token to propagate...")
        time.sleep(8)  # let the dev-buy land
    mint = record.mint

    # 2. burn the entire dev-buy allocation -> zero dev supply (if enabled)
    if not _reached(record, LaunchStatus.BURNED):
        if _settings.BURN_DEV_BUY:
            _log(record, "[burning] Burning dev buy tokens...")
            dev_balance = 0
            for _ in range(15):  # poll up to ~45s for the dev buy to actually land
                dev_balance = solana_client.get_token_balance_raw(record.deposit_wallet, mint)
                if dev_balance > 0:
                    break
                time.sleep(3)
            if dev_balance > 0:
                try:
                    decimals = distribution._mint_decimals(solana_client.client(), mint)
                    record.tx_burn = solana_client.burn_all(secret, mint, decimals, dev_balance)
                    _log(record, f"Burned {dev_balance} ({record.tx_burn})")
                except Exception as e:  # noqa: BLE001 — log but don't block the launch
                    _log(record, f"burn failed: {e}")
            else:
                _log(record, "No dev-buy tokens found to burn (skipped)")
        else:
            _log(record, "Dev buy kept (burn disabled)")

        # 2b. take the flat platform fee (e.g. 0.1 SOL) to the treasury
        if _settings.TREASURY_WALLET and _settings.PLATFORM_FEE_SOL > 0:
            try:
                solana_client.transfer_sol(secret, _settings.TREASURY_WALLET, _settings.PLATFORM_FEE_SOL)
                _log(record, f"Platform fee {_settings.PLATFORM_FEE_SOL} SOL -> treasury")
            except Exception as e:  # noqa: BLE001
                print(f"[{record.launch_id}] flat fee transfer failed: {e}")
        _set(record, LaunchStatus.BURNED)

    cashback_mode = _settings.DISTRIBUTION_MODE == "cashback"

    # 3. (auto mode only) swap remaining SOL budget into payout assets by weight.
    if not _reached(record, LaunchStatus.SWAPPED):
        if assets and not cashback_mode:
            bal_sol = solana_client.get_balance_sol(record.deposit_wallet)
            budget_lamports = int(max(bal_sol - 0.05, 0) * LAMPORTS_PER_SOL)  # keep gas buffer
            if budget_lamports < 1_000_000:  # < 0.001 SOL — nothing spare to swap
                _log(record, "[swapping] No spare SOL to swap yet — the basket is bought from creator fees each cycle.")
            else:
                _log(record, f"[swapping] Swapping {budget_lamports/LAMPORTS_PER_SOL:.4f} SOL into {len(assets)} assets...")
                alloc = _alloc(budget_lamports, assets, cfg.payout_weights)
                for sym in assets:
                    if alloc.get(sym, 0) < 1_000_000:  # < 0.001 SOL — dust leg, would just fail / buy nothing
                        continue
                    try:
                        jupiter.swap_sol_to_asset(secret, resolve_mint(sym), alloc[sym])
                        _log(record, f"{alloc[sym]/LAMPORTS_PER_SOL:.4f} SOL -> {sym}")
                        time.sleep(3)
                    except Exception as e:  # noqa: BLE001 — keep going on a single failed leg
                        _log(record, f"swap {sym} failed: {e}")
        _set(record, LaunchStatus.SWAPPED)

    # 4. cycles
    _set(record, LaunchStatus.DISTRIBUTING)
    if cashback_mode and record.cycles_done == 0:
        cashback.snapshot_and_accrue(record, 0)  # seed holder streaks at t0
    # let the coin trade & creator fees accrue before the FIRST distribution, so holders
    # have time to get in (skipped on resume, where cycles_done > 0)
    if record.cycles_done == 0 and _settings.FIRST_CYCLE_DELAY_SECONDS > 0:
        _log(record, f"[waiting] first distribution in ~{_settings.FIRST_CYCLE_DELAY_SECONDS // 60} min — letting the coin trade and fees build")
        time.sleep(_settings.FIRST_CYCLE_DELAY_SECONDS)
    for cycle in range(record.cycles_done, _settings.DISTRIBUTION_CYCLES):
        cycle_pool_lamports = 0
        try:
            pumpfun.claim_creator_fees(secret, record.mint)
            time.sleep(5)
            claimed = solana_client.get_balance_sol(record.deposit_wallet)
            record.fees_claimed_sol += claimed

            # 20% of fees -> treasury wallet (team buys back & burns $US manually, posts Solscan)
            burn_sol = claimed * _settings.BURN_FEE_BPS / 10_000
            if burn_sol > 0.001:
                _route_treasury_share(record, secret, burn_sol)

            holder_sol = max(claimed - burn_sol - 0.02, 0)  # keep gas buffer

            if cashback_mode:
                cycle_pool_lamports = int(holder_sol * LAMPORTS_PER_SOL)
            elif assets:
                alloc = _alloc(int(holder_sol * LAMPORTS_PER_SOL), assets, cfg.payout_weights)
                for sym in assets:
                    if alloc.get(sym, 0) < 1_000_000:  # < 0.001 SOL — dust leg
                        continue
                    try:
                        jupiter.swap_sol_to_asset(secret, resolve_mint(sym), alloc[sym])
                        time.sleep(3)
                    except Exception:
                        pass
        except Exception as e:  # noqa: BLE001
            print(f"[{record.launch_id}] fee cycle error: {e}")

        if cashback_mode:
            cashback.snapshot_and_accrue(record, cycle_pool_lamports)
        elif assets:
            holders = _eligible_holders(mint)
            for sym in assets:
                sent = distribution.distribute_asset(secret, resolve_mint(sym), holders)
                record.distributed[sym] = record.distributed.get(sym, 0) + len(sent)
                _log(record, f"--- Distributed {sym} to {len(sent)} holders --- OK")
                if len(sent):
                    try:
                        append_distribution({
                            "ts": int(time.time()),
                            "mint": record.mint,
                            "symbol": sym,
                            "asset_mint": resolve_mint(sym),
                            "amount_ui": getattr(sent, "amount_ui", 0.0),
                            "recipients": len(sent),
                            "source": "coin",
                        })
                    except Exception:  # noqa: BLE001 — stats logging must never block payouts
                        pass

        record.cycles_done = cycle + 1
        save_launch(record)

        if cycle < _settings.DISTRIBUTION_CYCLES - 1:
            time.sleep(_settings.CYCLE_INTERVAL_SECONDS)

    _set(record, LaunchStatus.COMPLETE)


def _bonding_curve_pda(mint: str) -> str:
    """The pump.fun bonding-curve PDA holds the unsold supply — never pay it."""
    try:
        bc, _ = _Pubkey.find_program_address(
            [b"bonding-curve", bytes(_Pubkey.from_string(mint))], _PUMP_FUN_PROGRAM
        )
        return str(bc)
    except Exception:  # noqa: BLE001
        return ""


def _eligible_holders(mint: str) -> dict[str, int]:
    """Real holders worth >= MIN_HOLD_USD of the launched token. Excludes the
    pump.fun bonding curve — it holds the unsold supply and would otherwise
    receive ~all of the basket instead of the actual holders."""
    holders = helius.get_holders(mint, min_raw=1)
    holders.pop(_bonding_curve_pda(mint), None)  # never distribute to the curve
    price = jupiter.token_price_usdc(mint, _settings.TOKEN_DECIMALS)
    if price > 0:
        min_raw = int(_settings.MIN_HOLD_USD / price * (10 ** _settings.TOKEN_DECIMALS))
        holders = {w: b for w, b in holders.items() if b >= min_raw}
    return holders


def _track_treasury(record: LaunchRecord, sol_amount: float) -> None:
    """Record this launch's cumulative contribution to the treasury (raw SOL + USD)."""
    record.treasury_sent_lamports += int(sol_amount * LAMPORTS_PER_SOL)
    try:
        px = jupiter.token_price_usdc(_SOL_MINT, 9)
        if px > 0:
            record.treasury_sent_usd += sol_amount * px
    except Exception:  # noqa: BLE001 — USD is best-effort; raw SOL is the source of truth
        pass


def _buyback_burn_main(record: LaunchRecord, secret: str, lamports: int) -> int:
    """Buy $US (MAIN_TOKEN_MINT) with `lamports` and burn what was bought.
    Requires $US to be Jupiter-routable. Returns the raw amount burned."""
    mint = _settings.MAIN_TOKEN_MINT
    c = solana_client.client()
    decimals, program_id = distribution._mint_info(c, mint)
    before = solana_client.get_token_balance_raw(record.deposit_wallet, mint, program_id)
    jupiter.swap_sol_to_asset(secret, mint, lamports)
    time.sleep(6)
    after = solana_client.get_token_balance_raw(record.deposit_wallet, mint, program_id)
    bought = after - before
    if bought > 0:
        sig = solana_client.burn_all(secret, mint, decimals, bought)
        try:
            append_burn({
                "ts": int(time.time()),
                "mint": mint,
                "amount_raw": int(bought),
                "amount_ui": bought / (10 ** decimals),
                "sol_spent": round(lamports / LAMPORTS_PER_SOL, 9),
                "signature": sig,
                "source_mint": record.mint,
                "source_symbol": getattr(record.config, "symbol", "") or "",
            })
        except Exception:  # noqa: BLE001 — proof logging must never block the burn
            pass
    return bought


def _route_treasury_share(record: LaunchRecord, secret: str, sol_amount: float) -> None:
    """Treasury share of each coin's fees. Controlled by TREASURY_MODE:
      - "wallet"     -> send the SOL to TREASURY_WALLET; team buys back & burns $US manually.
      - "distribute" -> buy TREASURY_ASSET (e.g. USDC) and distribute it pro-rata to $US holders.
    "distribute" needs MAIN_TOKEN_MINT set so $US holders can be enumerated; if it isn't set yet,
    we fall back to the wallet path so the share is never stranded. Either way the launch's cumulative
    contribution is tracked for the leaderboard."""
    if sol_amount <= 0:
        return
    lamports = int(sol_amount * LAMPORTS_PER_SOL)
    main_mint = _settings.MAIN_TOKEN_MINT

    # --- distribute mode: buy an asset and pay it to $US holders (Voult-style) ---
    if _settings.TREASURY_MODE == "distribute" and main_mint and _settings.TREASURY_ASSET:
        try:
            asset_mint = resolve_mint(_settings.TREASURY_ASSET)
            if not asset_mint:
                raise ValueError(f"unknown TREASURY_ASSET '{_settings.TREASURY_ASSET}'")
            jupiter.swap_sol_to_asset(secret, asset_mint, lamports)
            time.sleep(6)
            holders = _eligible_holders(main_mint)        # $US holders, $10 floor, curve excluded
            holders.pop(_settings.TREASURY_WALLET, None)  # never pay the treasury itself
            sent = distribution.distribute_asset(secret, asset_mint, holders)
            _track_treasury(record, sol_amount)
            _log(record, f"Treasury {sol_amount:.4f} SOL -> bought {_settings.TREASURY_ASSET}, paid {len(sent)} $US holder(s)")
            if len(sent):
                try:
                    append_distribution({
                        "ts": int(time.time()), "mint": main_mint, "symbol": _settings.TREASURY_ASSET,
                        "asset_mint": asset_mint, "amount_ui": getattr(sent, "amount_ui", 0.0),
                        "recipients": len(sent), "source": "treasury",
                    })
                except Exception:  # noqa: BLE001
                    pass
            return
        except Exception as e:  # noqa: BLE001
            _log(record, f"treasury distribute failed ({e}); routing to wallet instead")
            # fall through to the wallet path so the share is not lost

    # --- split mode: part buys & burns $US, the rest buys TREASURY_ASSET for $US holders ---
    if _settings.TREASURY_MODE == "split" and main_mint:
        pct = max(0, min(100, _settings.TREASURY_SPLIT_BURN_PCT))
        burn_sol = round(sol_amount * pct / 100, 9)
        dist_sol = round(sol_amount - burn_sol, 9)
        done = 0.0
        # leg 1: buy TREASURY_ASSET -> distribute to $US holders
        if dist_sol > 0.0005 and _settings.TREASURY_ASSET:
            try:
                asset_mint = resolve_mint(_settings.TREASURY_ASSET)
                if not asset_mint:
                    raise ValueError(f"unknown TREASURY_ASSET '{_settings.TREASURY_ASSET}'")
                jupiter.swap_sol_to_asset(secret, asset_mint, int(dist_sol * LAMPORTS_PER_SOL))
                time.sleep(6)
                holders = _eligible_holders(main_mint)
                holders.pop(_settings.TREASURY_WALLET, None)
                sent = distribution.distribute_asset(secret, asset_mint, holders)
                done += dist_sol
                _log(record, f"Treasury {dist_sol:.4f} SOL -> {_settings.TREASURY_ASSET} to {len(sent)} $US holder(s)")
                if len(sent):
                    try:
                        append_distribution({
                            "ts": int(time.time()), "mint": main_mint, "symbol": _settings.TREASURY_ASSET,
                            "asset_mint": asset_mint, "amount_ui": getattr(sent, "amount_ui", 0.0),
                            "recipients": len(sent), "source": "treasury",
                        })
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001
                _log(record, f"treasury {_settings.TREASURY_ASSET} leg failed: {e}")
        # leg 2: buy & burn $US
        if burn_sol > 0.0005:
            try:
                burned = _buyback_burn_main(record, secret, int(burn_sol * LAMPORTS_PER_SOL))
                done += burn_sol
                _log(record, f"Treasury {burn_sol:.4f} SOL -> bought & burned {burned} $US")
            except Exception as e:  # noqa: BLE001
                _log(record, f"treasury $US buy-burn leg failed: {e}")
        if done > 0:
            _track_treasury(record, done)
            return
        # both legs failed -> fall through to wallet

    # --- wallet mode (default / fallback) ---
    if not _settings.TREASURY_WALLET:
        return
    try:
        sig = solana_client.transfer_sol(secret, _settings.TREASURY_WALLET, sol_amount)
    except Exception as e:  # noqa: BLE001
        _log(record, f"treasury transfer failed: {e}")
        return
    _track_treasury(record, sol_amount)
    w = _settings.TREASURY_WALLET
    _log(record, f"Treasury share {sol_amount:.4f} SOL -> {w[:4]}..{w[-4:]} ({sig})")


def start_launch(record: LaunchRecord) -> None:
    def worker():
        acquired = _semaphore.acquire(blocking=True)
        try:
            _run(record)
        except Exception as e:  # noqa: BLE001
            record.error = f"{e}\n{traceback.format_exc()}"
            _set(record, LaunchStatus.FAILED)
        finally:
            if acquired:
                _semaphore.release()

    threading.Thread(target=worker, daemon=True).start()


# In-flight statuses that should be resumed after a host/process restart.
_RESUMABLE = {
    LaunchStatus.FUNDED,
    LaunchStatus.TOKEN_CREATED,
    LaunchStatus.BURNED,
    LaunchStatus.SWAPPED,
    LaunchStatus.DISTRIBUTING,
}


def resume_pending() -> int:
    """Re-launch any unfinished launches (called on app startup).
    _run is idempotent, so finished phases are skipped and cycles resume from cycles_done."""
    count = 0
    for record in list_launches():
        if record.status in _RESUMABLE:
            try:
                start_launch(record)
                count += 1
            except Exception as e:  # noqa: BLE001
                print(f"[resume] failed to resume {record.launch_id}: {e}")
    if count:
        print(f"[resume] resumed {count} in-flight launch(es)")
    return count
