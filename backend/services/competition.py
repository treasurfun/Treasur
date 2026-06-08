"""Daily competition.

$TREASUR's OWN pump.fun creator fees form a prize pool. Each period the pool is
split between:
  - Best Project — the launch that contributed the most to the treasury this period
  - Best Dev     — the owner whose launches contributed the most in total this period

It is funded entirely by $TREASUR's fees, independent of the 20% each coin routes
to the treasury, so it does not dilute the burn / holder distributions.

Activates only when MAIN_TOKEN_MINT is set AND a launch record exists for that mint
(i.e. $TREASUR was launched through Treasur, so its creator wallet is platform-
controlled and its fees can be claimed). Until then the scheduler safely no-ops.
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
_GAS_BUFFER_SOL = 0.01      # leave this on the $TREASUR wallet for rent/gas
_MIN_PRIZE_SOL = 0.002      # below this: skip and let fees + contributions accrue


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
    save_competition({"last_run_ts": int(time.time()), "initialized": True})
    print("[competition] initialized — clock started")


def run_competition() -> dict | None:
    """Run one payout. Returns the winners dict, or None if skipped (state unchanged)."""
    main_mint = _settings.MAIN_TOKEN_MINT
    if not main_mint:
        print("[competition] MAIN_TOKEN_MINT not set — skipped")
        return None
    rec = find_by_mint(main_mint)
    if not rec:
        print("[competition] no $TREASUR launch record (launch it through Treasur) — skipped")
        return None

    secret = decrypt_secret(rec.encrypted_secret)

    # 1) claim $TREASUR's own creator fees -> they land in its wallet (the prize pool)
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

    # 2) per-period contributions (delta since last payout), excluding $TREASUR itself
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

    best_rec, best_proj_delta = max(proj_deltas.values(), key=lambda x: x[1])
    best_dev_owner, best_dev_delta = max(dev_totals.items(), key=lambda x: x[1])

    # 3) split & pay (50/50 by default), from the $TREASUR wallet
    pct = max(0, min(100, _settings.COMPETITION_PROJECT_PCT))
    proj_prize = round(prize * pct / 100, 9)
    dev_prize = round(prize - proj_prize, 9)

    winners = {
        "last_run_ts": int(time.time()),
        "prize_sol": prize,
        "best_project": {
            "name": best_rec.config.name,
            "symbol": best_rec.config.symbol,
            "mint": best_rec.mint,
            "owner": best_rec.owner,
            "contributed_sol": round(best_proj_delta / 1e9, 6),
            "prize_sol": proj_prize,
            "tx": None,
        },
        "best_dev": {
            "owner": best_dev_owner,
            "contributed_sol": round(best_dev_delta / 1e9, 6),
            "prize_sol": dev_prize,
            "tx": None,
        },
    }

    if best_rec.owner and proj_prize > 0:
        try:
            winners["best_project"]["tx"] = solana_client.transfer_sol(secret, best_rec.owner, proj_prize)
            print(f"[competition] Best Project {best_rec.config.symbol} -> {_short(best_rec.owner)} {proj_prize} SOL")
        except Exception as e:  # noqa: BLE001
            print(f"[competition] best-project payout failed: {e}")
    if best_dev_owner and dev_prize > 0:
        try:
            winners["best_dev"]["tx"] = solana_client.transfer_sol(secret, best_dev_owner, dev_prize)
            print(f"[competition] Best Dev {_short(best_dev_owner)} -> {dev_prize} SOL")
        except Exception as e:  # noqa: BLE001
            print(f"[competition] best-dev payout failed: {e}")

    # 4) reset the period: snapshot every launch's cumulative total
    for l in launches:
        l.treasury_snapshot_lamports = l.treasury_sent_lamports
        try:
            save_launch(l)
        except Exception as e:  # noqa: BLE001
            print(f"[competition] snapshot save failed for {l.launch_id}: {e}")

    save_competition(winners)
    return winners


def _loop() -> None:
    """Run once per interval, surviving restarts by checking the persisted last-run
    time (so a redeploy can't reset a full day)."""
    time.sleep(30)  # let the app finish booting
    while True:
        try:
            if _settings.MAIN_TOKEN_MINT:
                state = load_competition()
                if not state.get("last_run_ts"):
                    _initialize()
                elif time.time() - state["last_run_ts"] >= _settings.COMPETITION_INTERVAL_SECONDS:
                    run_competition()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(min(_settings.COMPETITION_INTERVAL_SECONDS, 1800))


def start_scheduler() -> None:
    threading.Thread(target=_loop, name="competition", daemon=True).start()
    print("[competition] scheduler started")
