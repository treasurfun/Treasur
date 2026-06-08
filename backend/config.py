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
    # Dedicated Pinata gateway (e.g. mygw.mypinata.cloud). Far more reliable than the
    # shared gateway.pinata.cloud, which is rate-limited — pump.fun often fails to load
    # the token image through the shared one. Leave empty to use the shared gateway.
    PINATA_GATEWAY: str = os.getenv("PINATA_GATEWAY", "")

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
    MIN_FUNDING_SOL: float = float(os.getenv("MIN_FUNDING_SOL", "0.1"))    # required to deploy a coin
    PLATFORM_FEE_SOL: float = float(os.getenv("PLATFORM_FEE_SOL", "0"))    # flat fee (0 = off)
    # Split of each coin's ongoing creator fees:
    #   BURN_FEE_BPS  -> the "treasury share" (see TREASURY_MODE below)
    #   remainder     -> buy the chosen asset basket and distribute to that coin's holders
    BURN_FEE_BPS: int = int(os.getenv("BURN_FEE_BPS", "2000"))             # 20% treasury / 80% holders
    MAIN_TOKEN_MINT: str = os.getenv("MAIN_TOKEN_MINT", "")               # $TREASUR mint — required for treasury "distribute" mode
    TREASURY_WALLET: str = os.getenv("TREASURY_WALLET", "")               # the share lands here in "wallet" mode
    # What happens to the treasury share:
    #   "wallet"     -> send it to TREASURY_WALLET; team buys back & burns $TREASUR manually (posts Solscan)  [default]
    #   "distribute" -> auto-buy TREASURY_ASSET and distribute it pro-rata to $TREASUR holders
    #   "split"      -> do BOTH: part buys back & burns $TREASUR, the rest buys TREASURY_ASSET for $TREASUR holders
    #                   (distribute/split need MAIN_TOKEN_MINT; fall back to "wallet" if it isn't set yet)
    TREASURY_MODE: str = os.getenv("TREASURY_MODE", "wallet")
    TREASURY_ASSET: str = os.getenv("TREASURY_ASSET", "SPACEX")           # asset paid to $TREASUR holders in distribute/split mode
    TREASURY_SPLIT_BURN_PCT: int = int(os.getenv("TREASURY_SPLIT_BURN_PCT", "50"))  # split mode: % of the share that buys & burns $TREASUR; the rest buys TREASURY_ASSET for holders

    # Daily competition: $TREASUR's OWN creator fees form a prize pool, split between the
    # top project (most contributed to the treasury this period) and the top dev (best owner total).
    # Activates automatically once MAIN_TOKEN_MINT is set AND $TREASUR was launched through Treasur
    # (so its creator wallet is platform-controlled and its fees can be claimed).
    COMPETITION_INTERVAL_SECONDS: int = int(os.getenv("COMPETITION_INTERVAL_SECONDS", "86400"))  # 24h; 172800 = every other day
    COMPETITION_PROJECT_PCT: int = int(os.getenv("COMPETITION_PROJECT_PCT", "50"))  # % of the prize to Best Project; rest to Best Dev

    # ── Privy authentication (Phantom + email code + Twitter) ──
    # APP ID is public (it ships in the frontend bundle); APP SECRET must come from the
    # Railway env and is never committed. Verification key is a public key from the Privy
    # dashboard — if set, the access-token JWT is verified locally without a JWKS fetch.
    PRIVY_APP_ID: str = os.getenv("PRIVY_APP_ID", "cmq56wpb200170djmlxb2f1a4")
    PRIVY_APP_SECRET: str = os.getenv("PRIVY_APP_SECRET", "")
    PRIVY_VERIFICATION_KEY: str = os.getenv("PRIVY_VERIFICATION_KEY", "")  # optional PEM; else JWKS is used
    PRIVY_JWKS_URL: str = os.getenv("PRIVY_JWKS_URL", "")                  # optional override; else derived from app id
    PRIVY_API_BASE: str = os.getenv("PRIVY_API_BASE", "https://auth.privy.io/api/v1")
    SWAP_SLIPPAGE_BPS: int = int(os.getenv("SWAP_SLIPPAGE_BPS", "300"))  # 3%
    # Minimum holding (in USD) to be eligible for distributions ("$10 worth").
    MIN_HOLD_USD: float = float(os.getenv("MIN_HOLD_USD", "10"))

    # Concurrency
    MAX_CONCURRENT_LAUNCHES: int = int(os.getenv("MAX_CONCURRENT_LAUNCHES", "20"))
    DISTRIBUTION_CYCLES: int = int(os.getenv("DISTRIBUTION_CYCLES", "5"))
    CYCLE_INTERVAL_SECONDS: int = int(os.getenv("CYCLE_INTERVAL_SECONDS", "900"))   # gap between cycles (15 min)
    FIRST_CYCLE_DELAY_SECONDS: int = int(os.getenv("FIRST_CYCLE_DELAY_SECONDS", "300"))  # wait before the FIRST distribution (5 min) so the coin trades & holders can get in

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
