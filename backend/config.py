"""Configuration loaded from environment variables."""
import os
from functools import lru_cache


class Settings:
    # Branding — appended to every created coin's on-chain description.
    SITE_NAME: str = os.getenv("SITE_NAME", "treasur.fun")

    # Solana / RPC
    RPC_ENDPOINT: str = os.getenv("RPC_ENDPOINT", "https://api.mainnet-beta.solana.com")
    HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY", "")

    # PumpFun token creation (PumpPortal local-trade API by default)
    PUMPPORTAL_TRADE_URL: str = os.getenv(
        "PUMPPORTAL_TRADE_URL", "https://pumpportal.fun/api/trade-local"
    )
    # PumpDev API (used for token creation + fee claiming; PumpPortal trade-local
    # create is currently broken, returns 400 for valid requests).
    PUMPDEV_API_URL: str = os.getenv("PUMPDEV_API_URL", "https://pumpdev.io")
    # Pinata IPFS — required for token metadata (pump.fun /api/ipfs is deprecated)
    PINATA_JWT: str = os.getenv("PINATA_JWT", "")

    # Jupiter swap aggregator
    # Jupiter Swap API. The old quote-api.jup.ag/v6 domain is DEPRECATED (DNS no longer
    # resolves). Free tier is lite-api.jup.ag/swap/v1 (no key). Paths are v6-compatible.
    JUPITER_QUOTE_URL: str = os.getenv("JUPITER_QUOTE_URL", "https://lite-api.jup.ag/swap/v1/quote")
    JUPITER_SWAP_URL: str = os.getenv("JUPITER_SWAP_URL", "https://lite-api.jup.ag/swap/v1/swap")

    # Auth / admin
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "change-me")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # Used to encrypt private keys at rest. MUST be a 32-byte urlsafe-base64 Fernet key.
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # Storage
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")

    # Launch economics
    # No platform markup by default — creators pay only the real deploy cost.
    DEV_BUY_SOL: float = float(os.getenv("DEV_BUY_SOL", "0.01"))
    # Burn the dev-buy tokens after creation -> 0 dev supply ("can't rug"). The
    # trust signal, not the SOL amount, is the point. Set false to keep them.
    BURN_DEV_BUY: bool = os.getenv("BURN_DEV_BUY", "true").lower() == "true"
    MIN_FUNDING_SOL: float = float(os.getenv("MIN_FUNDING_SOL", "0.05"))   # ~deploy + gas, no markup
    PLATFORM_FEE_SOL: float = float(os.getenv("PLATFORM_FEE_SOL", "0"))    # flat fee (0 = off)
    # Split of each coin's ongoing creator fees:
    #   BURN_FEE_BPS  -> buy back your MAIN_TOKEN_MINT ($TREASUR) and BURN it
    #   remainder     -> buy the chosen asset basket and distribute to holders
    BURN_FEE_BPS: int = int(os.getenv("BURN_FEE_BPS", "2000"))             # 20% burn / 80% holders
    MAIN_TOKEN_MINT: str = os.getenv("MAIN_TOKEN_MINT", "")               # your $TREASUR main token (20% buyback+burn target)
    TREASURY_WALLET: str = os.getenv("TREASURY_WALLET", "")
    SWAP_SLIPPAGE_BPS: int = int(os.getenv("SWAP_SLIPPAGE_BPS", "300"))  # 3%
    # Minimum holding (in USD) to be eligible for distributions ("$10 worth").
    MIN_HOLD_USD: float = float(os.getenv("MIN_HOLD_USD", "10"))

    # Concurrency
    MAX_CONCURRENT_LAUNCHES: int = int(os.getenv("MAX_CONCURRENT_LAUNCHES", "20"))
    DISTRIBUTION_CYCLES: int = int(os.getenv("DISTRIBUTION_CYCLES", "5"))
    CYCLE_INTERVAL_SECONDS: int = int(os.getenv("CYCLE_INTERVAL_SECONDS", "3600"))

    # Distribution model
    # "auto"     => creator picks the asset basket + weights; fees buy that basket
    #               and distribute to holders pro-rata (matches voult.fun).
    # "cashback" => holders accrue claimable cashback gated by holding duration.
    DISTRIBUTION_MODE: str = os.getenv("DISTRIBUTION_MODE", "auto")
    MIN_HOLD_SECONDS: int = int(os.getenv("MIN_HOLD_SECONDS", str(7 * 86400)))  # 7 days
    MIN_HOLD_TOKENS: float = float(os.getenv("MIN_HOLD_TOKENS", "1"))            # min balance
    TOKEN_DECIMALS: int = int(os.getenv("TOKEN_DECIMALS", "6"))                  # pump.fun = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
