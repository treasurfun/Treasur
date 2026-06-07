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
from storage import save_launch, decrypt_secret, list_launches
from assets import resolve_mint
from services import solana_client, pumpfun, jupiter, helius, distribution, cashback

_settings = get_settings()
_semaphore = threading.Semaphore(_settings.MAX_CONCURRENT_LAUNCHES)
LAMPORTS_PER_SOL = 1_000_000_000


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
        mint, tx = pumpfun.create_token(secret, cfg, _settings.DEV_BUY_SOL)
        record.mint = mint
        record.tx_create = tx
        _set(record, LaunchStatus.TOKEN_CREATED)
        _log(record, f"Created: {mint}")
        _log(record, "[waiting] Waiting 8s for token to propagate...")
        time.sleep(8)  # let the dev-buy land
    mint = record.mint

    # 2. burn the entire dev-buy allocation -> zero dev supply (if enabled)
    if not _reached(record, LaunchStatus.BURNED):
        if _settings.BURN_DEV_BUY:
            _log(record, "[burning] Burning dev buy tokens...")
            dev_balance = solana_client.get_token_balance_raw(record.deposit_wallet, mint)
            if dev_balance > 0:
                decimals = distribution._mint_decimals(solana_client.client(), mint)
                record.tx_burn = solana_client.burn_all(secret, mint, decimals, dev_balance)
                _log(record, f"Burned {dev_balance} ({record.tx_burn})")
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
            _log(record, f"[swapping] Swapping {budget_lamports/LAMPORTS_PER_SOL:.4f} SOL into {len(assets)} assets...")
            alloc = _alloc(budget_lamports, assets, cfg.payout_weights)
            for sym in assets:
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
    for cycle in range(record.cycles_done, _settings.DISTRIBUTION_CYCLES):
        cycle_pool_lamports = 0
        try:
            pumpfun.claim_creator_fees(secret)
            time.sleep(5)
            claimed = solana_client.get_balance_sol(record.deposit_wallet)
            record.fees_claimed_sol += claimed

            # burn portion of fees: buy back the coin (or protocol token) and burn it
            burn_sol = claimed * _settings.BURN_FEE_BPS / 10_000
            if burn_sol > 0.001:
                _buyback_and_burn(record, secret, burn_sol)

            holder_sol = max(claimed - burn_sol - 0.02, 0)  # keep gas buffer

            if cashback_mode:
                cycle_pool_lamports = int(holder_sol * LAMPORTS_PER_SOL)
            elif assets:
                alloc = _alloc(int(holder_sol * LAMPORTS_PER_SOL), assets, cfg.payout_weights)
                for sym in assets:
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

        record.cycles_done = cycle + 1
        save_launch(record)

        if cycle < _settings.DISTRIBUTION_CYCLES - 1:
            time.sleep(_settings.CYCLE_INTERVAL_SECONDS)

    _set(record, LaunchStatus.COMPLETE)


def _eligible_holders(mint: str) -> dict[str, int]:
    """Holders worth at least MIN_HOLD_USD of the launched token."""
    holders = helius.get_holders(mint, min_raw=1)
    price = jupiter.token_price_usdc(mint, _settings.TOKEN_DECIMALS)
    if price > 0:
        min_raw = int(_settings.MIN_HOLD_USD / price * (10 ** _settings.TOKEN_DECIMALS))
        holders = {w: b for w, b in holders.items() if b >= min_raw}
    return holders


def _buyback_and_burn(record: LaunchRecord, secret: str, sol_amount: float) -> None:
    """Use `sol_amount` SOL to buy back your $TREASUR main token and burn it.
    Until MAIN_TOKEN_MINT is set, the burn share accrues in the treasury."""
    lamports = int(sol_amount * LAMPORTS_PER_SOL)
    mint = _settings.MAIN_TOKEN_MINT
    if not mint:
        if _settings.TREASURY_WALLET:
            try:
                solana_client.transfer_sol(secret, _settings.TREASURY_WALLET, sol_amount)
                _log(record, f"Burn share {sol_amount:.4f} SOL -> treasury (main token not set yet)")
            except Exception as e:  # noqa: BLE001
                _log(record, f"burn-share transfer failed: {e}")
        return
    try:
        c = solana_client.client()
        decimals, program_id = distribution._mint_info(c, mint)
        before = solana_client.get_token_balance_raw(record.deposit_wallet, mint, program_id)
        jupiter.swap_sol_to_asset(secret, mint, lamports)
        time.sleep(6)
        after = solana_client.get_token_balance_raw(record.deposit_wallet, mint, program_id)
        bought = after - before
        if bought > 0:
            solana_client.burn_all(secret, mint, decimals, bought)
            _log(record, f"Buyback+burn {sol_amount:.4f} SOL -> burned {bought} $TREASUR")
    except Exception as e:  # noqa: BLE001
        _log(record, f"buyback/burn failed: {e}")


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
