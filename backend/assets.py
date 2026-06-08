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
        # ── added xStocks — official mints from solana.com/news/case-study-xstocks
        #    (each verifiable on Solscan; Token-2022, same as the rest of this group) ──
        "COIN": "Xs7ZdzSHLU9ftNJsii5fCeJhoRWSC32SQGzGQtePxNu",   # Coinbase
        "CRCL": "XsueG8BtpquVJX9LVLLEGuViXUungE6WmK5YZ3p3bd1",   # Circle
        "PLTR": "XsoBhf2ufR8fTyNSjqfU71DYGaE6Z3SUGAidpzriAA4",   # Palantir
        "APP": "XsPdAVBi8Zc1xvv53k4JcMrQaEDTgkGqKYeh7AYgPHV",    # AppLovin
        "ORCL": "XsjFwUPiLofddX5cWFHW35GCbXcSu1BCUGfxoQAQjeL",   # Oracle
        "INTC": "XshPgPdXFRWB8tP1j82rebb2Q9rPgGX37RuqzohmArM",   # Intel
        "IBM": "XspwhyYPdWVM8XBHZnpS9hgyag9MKjLRyE3tVfmCbSr",    # IBM
        "CSCO": "Xsr3pdLQyXvDJBFgpR5nexCEZwXvigb8wbPYp4YoNFf",   # Cisco
        "MRVL": "XsuxRGDzbLjnJ72v74b7p9VY6N66uYgTCyfwwRjVCJA",   # Marvell
        "JPM": "XsMAqkcKsUewDrzVkait4e5u4y8REgtyS7jWgCpLV2C",    # JPMorgan Chase
        "BAC": "XswsQk4duEQmCbGzfqUUWYmi7pV7xpJ9eEmLHXCaEQP",    # Bank of America
        "GS": "XsgaUyp4jd1fNBCxgtTKkW64xnnhQcvgaxzsbAq5ZD1",     # Goldman Sachs
        "MA": "XsApJFV9MAktqnAc6jqzsHVujxkGm9xcSUffaBoYLKC",     # Mastercard
        "BRKB": "Xs6B6zawENwAbWVi7w92rjazLuAr5Az59qgWKcNb45x",   # Berkshire Hathaway (BRK.B)
        "KO": "XsaBXg8dU5cPM6ehmVctMkVqoiRG2ZjMo1cyBJ3AykQ",     # Coca-Cola
        "PEP": "Xsv99frTRUeornyvCfvhnDesQDWuvns1M852Pez91vF",    # PepsiCo
        "MCD": "XsqE9cRRpzxcGKDXj1BJ7Xmg4GRhZoyY1KpmGSxAWT2",    # McDonald's
        "WMT": "Xs151QeqTCiuKtinzfRATnUESM2xTU6V9Wy8Vy538ci",    # Walmart
        "HD": "XszjVtyhowGjSC5odCqBpW1CtXXwXjYokymrk7fGKD3",     # Home Depot
        "PG": "XsYdjDjNUygZ7yGKfQaB6TxLh2gC6RRjzLtLAGJrhzV",     # Procter & Gamble
        "PM": "Xsba6tUnSjDae2VcopDB6FGGDaxRrewFCDa5hKn5vT3",     # Philip Morris
        "JNJ": "XsGVi5eo1Dh2zUpic4qACcjuWGjNv8GCt3dm5XcX6Dn",    # Johnson & Johnson
        "PFE": "XsAtbqkAP1HJxy7hFDeq7ok6yM43DQ9mQ1Rh861X8rw",    # Pfizer
        "LLY": "Xsnuv4omNoHozR6EEW5mXkw8Nrny5rB3jVfLqi6gKMH",    # Eli Lilly
        "MRK": "XsnQnU7AdbRZYe2akqqpibDdXjkieGFfSkbkjX1Sd1X",    # Merck
        "UNH": "XszvaiXGPwvk2nwb3o9C1CX4K6zH8sez11E6uyup6fe",    # UnitedHealth
        "ABBV": "XswbinNKyPmzTa5CskMbCPvMW6G5CMnZXZEeQSSQoie",   # AbbVie
        "ABT": "XsHtf5RpxsQ7jeJ9ivNewouZKJHbPxhPoEy6yYvULr7",    # Abbott
        "DHR": "Xseo8tgCZfkHxWS9xbFYeKFyMSbWEvZGFV1Gh53GtCV",    # Danaher
        "MDT": "XsDgw22qRLTv5Uwuzn6T63cW69exG41T6gwQhEK22u2",    # Medtronic
        "TMO": "Xs8drBWy3Sd5QY3aifG9kt9KFs2K3PGZmx7jWrsrk57",    # Thermo Fisher
        "NVO": "XsfAzPzYrYjd4Dpa9BU3cusBsvWfVB9gBcyGC87S57n",    # Novo Nordisk
        "AZN": "Xs3ZFkPYT2BN7qBMqf1j1bfTeTm1rFzEFSsQ1z3wAKU",    # AstraZeneca
        "ACN": "Xs5UJzmCRQ8DWZjskExdSQDnbE6iLkRu2jjrRAB1JSU",    # Accenture
        "HON": "XsRbLZthfABAPAfumWNEJhPyiKDW6TvDVeAeW7oKqA2",    # Honeywell
        "LIN": "XsSr8anD1hkvNMu8XQiVcmiaTP7XGvYu7Q58LdmtE8Z",    # Linde
        "XOM": "XsaHND8sHyfMfsWPj6kSdd5VwvCayZvjYgKmmcNL5qh",    # Exxon Mobil
        "CVX": "XsNNMt7WTNA2sV3jrb1NNfNgapxRF5i4i6GcnTRRHts",    # Chevron
        "QQQ": "Xs8S1uUs1zvS2p7iwtsG3b6fkhpvmwz4GYU3gWAmWHZ",    # Nasdaq-100 ETF
        "VTI": "XsssYEQjzxBCFgvYFFNuhJFBeHNdLWYeUSP8F45cDr9",    # Vanguard Total US Market ETF
        "SNDK": "",  # no xStock issued for SanDisk yet — leave blank
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
