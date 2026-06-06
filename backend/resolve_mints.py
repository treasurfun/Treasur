"""Suggest mint addresses for the catalog symbols from Jupiter's token list.

Run:  python resolve_mints.py

This is a HELPER, not an authority. It prints candidate mints so you don't hand-
type 40 addresses. ALWAYS confirm each on Solscan before pasting into assets.py —
a wrong mint sends funds into the void.

xStocks tickers end in "x" (AAPL -> AAPLx), so stocks are searched with that
suffix. Crypto/commodities are searched by their plain symbol.
"""
import httpx

from assets import ASSETS, XSTOCK_SYMBOLS

JUP_TOKENS = "https://tokens.jup.ag/tokens?tags=verified"


def build_index() -> dict[str, list[dict]]:
    data = httpx.get(JUP_TOKENS, timeout=60).json()
    idx: dict[str, list[dict]] = {}
    for t in data:
        idx.setdefault(t.get("symbol", "").upper(), []).append(t)
    return idx


def main():
    idx = build_index()
    print(f"{'SYMBOL':<8} {'SEARCH':<8} CANDIDATE MINT(S)")
    print("-" * 70)
    for group, items in ASSETS.items():
        for sym in items:
            # xStocks are searched as e.g. AAPLx; PreStocks / crypto by plain symbol
            search = (sym + "x").upper() if sym in XSTOCK_SYMBOLS else sym.upper()
            hits = idx.get(search, [])
            if not hits:
                print(f"{sym:<8} {search:<8} (no verified match — find on Solscan/RWA.xyz)")
            for h in hits[:3]:
                print(f"{sym:<8} {search:<8} {h['address']}  ({h.get('name','')})")


if __name__ == "__main__":
    main()
