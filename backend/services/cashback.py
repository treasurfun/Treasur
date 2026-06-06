"""Holder cashback (loyalty redemption).

Each distribution cycle, the creator fees left after the platform cut are added
to a SOL-denominated cashback pool and shared — pro-rata by current balance —
among holders who have held continuously for at least MIN_HOLD_SECONDS with at
least MIN_HOLD_TOKENS. Eligible holders can later claim their accrued cashback,
converted via Jupiter into a PreStock (or any supported asset) and sent to their
own wallet.

Holding duration is tracked from periodic Helius snapshots: a wallet that drops
below the minimum balance breaks its streak and restarts when it returns.
"""
import time

from config import get_settings
from models import LaunchRecord, HolderState, CashbackStatus
from storage import save_launch, decrypt_secret
from assets import resolve_mint
from services import helius, jupiter, solana_client, distribution

_settings = get_settings()
LAMPORTS_PER_SOL = 1_000_000_000


def _min_raw() -> int:
    return int(_settings.MIN_HOLD_TOKENS * (10 ** _settings.TOKEN_DECIMALS))


def _is_eligible(h: HolderState, now: float) -> bool:
    return (
        h.first_seen is not None
        and h.balance >= _min_raw()
        and (now - h.first_seen) >= _settings.MIN_HOLD_SECONDS
    )


def snapshot_and_accrue(record: LaunchRecord, cycle_pool_lamports: int) -> None:
    """Refresh holder snapshot, update holding streaks, and accrue this cycle's
    pool to currently-eligible holders."""
    if not record.mint:
        return
    now = time.time()
    current = helius.get_holders(record.mint, min_raw=1)  # {wallet: raw balance}
    owner = record.deposit_wallet

    # update / create states for current holders
    for wallet, bal in current.items():
        if wallet == owner:
            continue
        h = record.holders.get(wallet) or HolderState()
        if bal >= _min_raw():
            if h.first_seen is None:
                h.first_seen = now           # streak starts
        else:
            h.first_seen = None              # below threshold -> no streak
        h.balance = bal
        h.last_seen = now
        record.holders[wallet] = h

    # holders that fully exited since last snapshot -> break streak
    for wallet, h in record.holders.items():
        if wallet not in current:
            h.balance = 0
            h.first_seen = None

    # accrue this cycle's pool to eligible holders, pro-rata by balance
    eligible = {w: h for w, h in record.holders.items() if _is_eligible(h, now)}
    total = sum(h.balance for h in eligible.values())
    if cycle_pool_lamports > 0 and total > 0:
        for w, h in eligible.items():
            h.accrued_lamports += cycle_pool_lamports * h.balance // total
        record.cashback_pool_lamports += cycle_pool_lamports

    save_launch(record)


def status(record: LaunchRecord, wallet: str) -> CashbackStatus:
    now = time.time()
    h = record.holders.get(wallet) or HolderState()
    held = (now - h.first_seen) if h.first_seen else 0
    return CashbackStatus(
        wallet=wallet,
        balance=h.balance,
        eligible=_is_eligible(h, now),
        accrued_sol=h.accrued_lamports / LAMPORTS_PER_SOL,
        claimed_sol=h.claimed_lamports / LAMPORTS_PER_SOL,
        seconds_held=held,
        seconds_required=_settings.MIN_HOLD_SECONDS,
    )


def claim(record: LaunchRecord, wallet: str, asset_symbol: str) -> tuple[str, float]:
    """Convert a holder's accrued cashback into `asset_symbol` and send it to
    their wallet. Returns (tx_signature, sol_spent)."""
    now = time.time()
    h = record.holders.get(wallet)
    if not h or not _is_eligible(h, now):
        raise ValueError("Wallet is not eligible yet (hold longer / hold more).")
    amount_lamports = h.accrued_lamports
    if amount_lamports <= 0:
        raise ValueError("No cashback accrued.")

    mint = resolve_mint(asset_symbol)
    secret = decrypt_secret(record.encrypted_secret)

    # convert SOL -> asset on the launch wallet, then forward the received amount
    c = solana_client.client()
    _, program_id = distribution._mint_info(c, mint)
    before = solana_client.get_token_balance_raw(record.deposit_wallet, mint, program_id)
    jupiter.swap_sol_to_asset(secret, mint, amount_lamports)
    time.sleep(6)
    after = solana_client.get_token_balance_raw(record.deposit_wallet, mint, program_id)
    received = after - before
    if received <= 0:
        raise RuntimeError("Swap produced no output (route/liquidity).")

    tx = distribution.transfer_token_to(secret, mint, wallet, received)

    h.accrued_lamports = 0
    h.claimed_lamports += amount_lamports
    save_launch(record)
    return tx, amount_lamports / LAMPORTS_PER_SOL
