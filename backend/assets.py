"""Registry of supported payout assets — matched to the live voult.fun catalog.

IMPORTANT — fill in VERIFIED mints before going live. A wrong mint loses funds.
Run `python resolve_mints.py` to pull candidates from Jupiter's token list, then
confirm each on Solscan.

Groups (as shown in the app):
  crypto         classic SPL (BTC/ETH/ZEC/PUMP/HYPE wrapped) + USDC
  commodities    tokenized GOLD / SILVER / OIL
  stocks         xStocks public equities (SPL Token-2022, ticker = symbol + "x")
  stocks_preipo  PreStocks pre-IPO (classic SPL): SpaceX, Kalshi, Anthropic, OpenAI

Distribution auto-detects the token program per mint, so SPL and Token-2022
both work. See README for the jurisdiction / Token-2022 / PreStocks caveats.
"""

WSOL_MINT = "So11111111111111111111111111111111111111112"

ASSETS = {
    "crypto": {
        "BTC": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",   # wrapped BTC (Portal) — verify
        "ETH": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",   # wrapped ETH (Portal) — verify
        "ZEC": "", "PUMP": "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn", "HYPE": "",
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC mainnet — verify
    },
    "commodities": {
        "GOLD": "Xsv9hRk1z5ystj9MhnA7Lq4vjSsLwzL2nxrwmwtD3re",  # GLDx (Gold xStock) — verify
        # SLVON = iShares Silver Trust, Ondo-tokenized (Ondo Global Markets). Liquid on
        # Jupiter (~$33M mcap, ~$4M daily vol). This is the silver token voult.fun uses.
        "SILVER": "iy11ytbSGcUnrjE6Lfv78TFqxKyUESfku1FugS9ondo",
        # No safe, liquid spot oil token on Solana — oil trades as PERPS on Hyperliquid,
        # and the "oil" SPLs are memes/scams. Leave blank; a wrong mint loses funds.
        "OIL": "",
    },
    # xStocks public equities (Token-2022). Mints from the official Solana
    # case study (solana.com/news/case-study-xstocks) — VERIFY on Solscan before live.
    "stocks": {
        "GME": "Xsf9mBktVB9BSU5kf4nHxPq5hCBJ2j2ui3ecFGxPRGc",
        "MSTR": "XsP7xzNPvEHS1m6qfanPUGjNmdnmsLKEoNAnHjdxxyZ",
        "HOOD": "XsvNBAYkrDRNhA7wPHQfX3ZUXZyZLdnCQDfHZ56bzpg",
        "AAPL": "XsbEhLAtcf6HdfpFZ5xEMdqW8nfAvcsP5bdudRLJzJp",
        "GOOGL": "XsCPL9dNWBMvFtTmwcCA5v3xWPSMEBCszbQdiLLq6aN",
        "NVDA": "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh",
        "AMZN": "Xs3eBt7uRfJX8QUs4suhyU8p2M6DoUDrJyWBa8LLZsg",
        "MSFT": "XspzcW1PRtgf6Wj92HCiZdjzKCyFekVD8P5Ueh3dRMX",
        "TSLA": "XsDoVfqeBukxuZHWhdvWHBhgEHjGNst4MLodqsJHzoB",
        "META": "Xsa62P5mvPszXL1krVUnU5ar38bBSVcWAB6fmPCo5Zu",
        "CRM": "XsczbcQ3zfcgAEt9qHQES8pxKAVG5rujPSHQEXi4kaN",
        "AVGO": "XsgSaSvNSqLTtFuyWPBhK9196Xb9Bbdyjj4fH3cPJGo",
        "NFLX": "XsEH7wWfJJu2ZT3UCFeVfALnVA6CP5ur7Ee11KmzVpL",
        "V": "XsqgsbXwWogGJsNcVZ3TyVouy2MbTkfCFhCGGGcQZ2p",
        "CRWD": "Xs7xXqkcK7K8urEqGg52SECi79dRp2cEKKuYjUePYDw",
        "CMCSA": "XsvKCaNsxg2GN8jjUmq71qukMJr7Q1c5R2Mk9P8kcS8",
        "SP500": "XsoCS1TfEyfFhfvj8EtZ528L3CaKBDBRqRapnBbDF2W",  # SPYx (S&P 500 ETF)
        # ── user-selected additions (xStocks Token-2022; VERIFY each on Solscan/Jupiter before live) ──
        "COIN": "Xs7ZdzSHLU9ftNJsii5fCeJhoRWSC32SQGzGQtePxNu",   # Coinbase
        "PLTR": "XsoBhf2ufR8fTyNSjqfU71DYGaE6Z3SUGAidpzriAA4",   # Palantir
        "ORCL": "XsjFwUPiLofddX5cWFHW35GCbXcSu1BCUGfxoQAQjeL",   # Oracle
        "JPM": "XsMAqkcKsUewDrzVkait4e5u4y8REgtyS7jWgCpLV2C",    # JPMorgan
        "GS": "XsgaUyp4jd1fNBCxgtTKkW64xnnhQcvgaxzsbAq5ZD1",     # Goldman Sachs
        "MA": "XsApJFV9MAktqnAc6jqzsHVujxkGm9xcSUffaBoYLKC",     # Mastercard
        "JNJ": "XsGVi5eo1Dh2zUpic4qACcjuWGjNv8GCt3dm5XcX6Dn",    # Johnson & Johnson
        "WMT": "Xs151QeqTCiuKtinzfRATnUESM2xTU6V9Wy8Vy538ci",    # Walmart
    },
    # PreStocks pre-IPO (classic SPL, traded on Jupiter). Mints from prestocks.com/products.
    "stocks_preipo": {
        "SPACEX": "PreANxuXjsy2pvisWWMNB6YaJNzr7681wJJr2rHsfTh",
        "ANTHROPIC": "Pren1FvFX6J3E4kXhJuCiAD5aDmGEb7qJRncwA8Lkhw",
        "OPENAI": "PreweJYECqtQwBtpxHL171nL2K6umo692gTm7Q3rpgF",
        "NEURALINK": "PrekqLJvJ3qVdXmBGDiexvwUTF4rLFDa6HWS4HJbw9S",
        "KALSHI": "PreLWGkkeqG1s4HEfFZSy9moCrJ7btsHuUtfcCeoRua",
        "POLYMARKET": "Pre8AREmFPtoJFT8mQSXQLh56cwJmM7CFDRuoGBZiUP",
    },
}

# xStocks are Token-2022 and are resolved by searching "<symbol>x" on Jupiter.
XSTOCK_SYMBOLS = set(ASSETS["stocks"].keys())
TOKEN_2022_SYMBOLS = set(ASSETS["stocks"].keys())   # informational; distribution auto-detects
PREIPO_SYMBOLS = set(ASSETS["stocks_preipo"].keys())


def resolve_mint(symbol: str) -> str:
    symbol = symbol.upper()
    for group in ASSETS.values():
        if symbol in group and group[symbol]:
            return group[symbol]
    raise KeyError(f"Unknown or unconfigured asset symbol: {symbol}")


def is_token2022(symbol: str) -> bool:
    return symbol.upper() in TOKEN_2022_SYMBOLS


def all_symbols() -> list[str]:
    out = []
    for group in ASSETS.values():
        out.extend(group.keys())
    return out
