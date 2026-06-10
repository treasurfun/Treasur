"""Daily competition.

$US's OWN pump.fun creator fees form a prize pool ("farmed fees"). Each period
the pool is split between:
  - Best Dev     — the owner whose launches contributed the most in total this period
                   (the primary award; decided first)
  - Best Project — the single launch that contributed the most this period, owned by a
                   DIFFERENT dev than the Best Dev (nobody can take both spots)

Funded entirely by $US's own fees, independent of the 20% each coin routes to the
treasury, so it doesn't dilute the burn / holder distributions.

Activates only when MAIN_TOKEN_MINT is set AND a launch record exists for that mint
(i.e. $US was launched through Unstable Safe, so its creator wallet is platform-controlled
and its fees can be claimed). Until then the scheduler safely no-ops.
"""
import threading
import time
import traceback

from config import get_settings
from storage import (
    list_launches,
    find_by_mint,
    decrypt_secret,
    save_launch,
    load_competition,
    save_competition,
)
from services import solana_client, pumpfun

_settings = get_settings()
_GAS_BUFFER_SOL = 0.01      # leave this on the $US wallet for rent/gas
_MIN_PRIZE_SOL = 0.002      # below this: skip and let fees + contributions accrue
_POOL_CLAIM_EVERY = 3600    # claim accrued $US fees into the wallet at most hourly


def _short(a: str) -> str:
    return f"{a[:4]}..{a[-4:]}" if a and len(a) > 8 else (a or "")


def _initialize() -> None:
    """First activation: start the clock and snapshot current totals so the first
    payout only counts contributions made during the first period."""
    for l in list_launches():
        if l.mint:
            l.treasury_snapshot_lamports = l.treasury_sent_lamports
            try:
                save_launch(l)
            except Exception:  # noqa: BLE001
                pass
    state = load_competition()
    state.update({"last_run_ts": int(time.time()), "initialized": True})
    save_competition(state)
    print("[competition] initialized — clock started")


def _refresh_pool() -> None:
    """Best-effort: claim $US's accrued creator fees into its wallet (throttled) and
    record the current pot size, so the UI can show the live prize pool between payouts."""
    main_mint = _settings.MAIN_TOKEN_MINT
    if not main_mint:
        return
    rec = find_by_mint(main_mint)
    if not rec:
        return
    try:
        state = load_competition()
        now = time.time()
        if now - state.get("last_pool_claim_ts", 0) >= _POOL_CLAIM_EVERY:
            try:
                pumpfun.claim_creator_fees(decrypt_secret(rec.encrypted_secret))
            except Exception:  # noqa: BLE001 — nothing to claim / transient
                pass
            state["last_pool_claim_ts"] = now
        pool = round(max(solana_client.get_balance_sol(rec.deposit_wallet) - _GAS_BUFFER_SOL, 0.0), 9)
        state["pool_sol"] = pool
        save_competition(state)
    except Exception as e:  # noqa: BLE001
        print(f"[competition] pool refresh failed: {e}")


def run_competition() -> dict | None:
    """Run one payout. Returns the winners dict, or None if skipped (state unchanged)."""
    main_mint = _settings.MAIN_TOKEN_MINT
    if not main_mint:
        print("[competition] MAIN_TOKEN_MINT not set — skipped")
        return None
    rec = find_by_mint(main_mint)
    if not rec:
        print("[competition] no $US launch record (launch it through Unstable Safe) — skipped")
        return None

    secret = decrypt_secret(rec.encrypted_secret)

    # 1) claim any remaining $US creator fees -> the wallet holds the full pot
    try:
        pumpfun.claim_creator_fees(secret)
        time.sleep(8)
    except Exception as e:  # noqa: BLE001
        print(f"[competition] fee claim failed (using current balance): {e}")

    pool = solana_client.get_balance_sol(rec.deposit_wallet)
    prize = round(max(pool - _GAS_BUFFER_SOL, 0.0), 9)
    if prize < _MIN_PRIZE_SOL:
        print(f"[competition] prize too small ({prize} SOL) — skipped, accruing")
        return None

    # 2) per-period contributions (delta since last payout), excluding $US itself
    launches = [l for l in list_launches() if l.mint and l.mint != main_mint]
    proj_deltas: dict[str, tuple] = {}   # launch_id -> (record, delta_lamports)
    dev_totals: dict[str, int] = {}      # owner -> total delta_lamports
    for l in launches:
        d = l.treasury_sent_lamports - (l.treasury_snapshot_lamports or 0)
        if d <= 0:
            continue
        proj_deltas[l.launch_id] = (l, d)
        if l.owner:
            dev_totals[l.owner] = dev_totals.get(l.owner, 0) + d

    if not proj_deltas:
        print("[competition] no contributions this period — skipped")
        return None

    # 3) winners — Best Dev first (primary), then Best Project from a DIFFERENT owner
    best_dev_owner, best_dev_delta = max(dev_totals.items(), key=lambda x: x[1])
    others = [(l, d) for (l, d) in proj_deltas.values() if l.owner != best_dev_owner]
    if others:
        best_rec, best_proj_delta = max(others, key=lambda x: x[1])
    else:
        best_rec, best_proj_delta = None, 0  # only one dev in play -> they can't win twice

    # 4) split & pay, from the $US wallet
    pct = max(0, min(100, _settings.COMPETITION_PROJECT_PCT))
    if best_rec is None:
        proj_prize, dev_prize = 0.0, prize       # single dev: takes the whole pot once
    else:
        proj_prize = round(prize * pct / 100, 9)
        dev_prize = round(prize - proj_prize, 9)

    winners: dict = {
        "last_run_ts": int(time.time()),
        "prize_sol": prize,
        "best_dev": {
            "owner": best_dev_owner,
            "contributed_sol": round(best_dev_delta / 1e9, 6),
            "prize_sol": dev_prize,
            "tx": None,
        },
        "best_project": None,
    }
    if best_rec is not None:
        winners["best_project"] = {
            "name": best_rec.config.name,
            "symbol": best_rec.config.symbol,
            "mint": best_rec.mint,
            "owner": best_rec.owner,
            "contributed_sol": round(best_proj_delta / 1e9, 6),
            "prize_sol": proj_prize,
            "tx": None,
        }

    if best_dev_owner and dev_prize > 0:
        try:
            winners["best_dev"]["tx"] = solana_client.transfer_sol(secret, best_dev_owner, dev_prize)
            print(f"[competition] Best Dev {_short(best_dev_owner)} -> {dev_prize} SOL")
        except Exception as e:  # noqa: BLE001
            print(f"[competition] best-dev payout failed: {e}")
    if best_rec is not None and best_rec.owner and proj_prize > 0:
        try:
            winners["best_project"]["tx"] = solana_client.transfer_sol(secret, best_rec.owner, proj_prize)
            print(f"[competition] Best Project {best_rec.config.symbol} -> {_short(best_rec.owner)} {proj_prize} SOL")
        except Exception as e:  # noqa: BLE001
            print(f"[competition] best-project payout failed: {e}")

    # 5) reset the period: snapshot every launch's cumulative total
    for l in launches:
        l.treasury_snapshot_lamports = l.treasury_sent_lamports
        try:
            save_launch(l)
        except Exception as e:  # noqa: BLE001
            print(f"[competition] snapshot save failed for {l.launch_id}: {e}")

    # 6) merge into state (keep pool/claim bookkeeping), bump cumulative total
    state = load_competition()
    paid = dev_prize + (proj_prize if best_rec is not None else 0.0)
    state.update(winners)
    state["total_distributed_sol"] = round(state.get("total_distributed_sol", 0.0) + paid, 9)
    state["pool_sol"] = round(max(solana_client.get_balance_sol(rec.deposit_wallet) - _GAS_BUFFER_SOL, 0.0), 9)
    save_competition(state)
    return winners


def _loop() -> None:
    """Run once per interval (surviving restarts via the persisted last-run time), and
    refresh the live pool each iteration."""
    time.sleep(30)  # let the app finish booting
    while True:
        try:
            if _settings.MAIN_TOKEN_MINT:
                state = load_competition()
                if not state.get("last_run_ts"):
                    _initialize()
                elif time.time() - state["last_run_ts"] >= _settings.COMPETITION_INTERVAL_SECONDS:
                    run_competition()
                _refresh_pool()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(min(_settings.COMPETITION_INTERVAL_SECONDS, 1800))


def start_scheduler() -> None:
    threading.Thread(target=_loop, name="competition", daemon=True).start()
    print("[competition] scheduler started")
