"""Jupiter Aggregator v6 swap integration.

Flow: get a quote for SOL -> target mint, request a swap transaction built for
the launch wallet, sign it locally, and submit. Used both to convert the launch
budget into payout assets and (optionally) reinvested fees.
"""
import base64
import httpx

from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from config import get_settings
from services.solana_client import keypair_from_secret, client
from assets import WSOL_MINT

_settings = get_settings()


def get_quote(input_mint: str, output_mint: str, amount_raw: int) -> dict:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_raw),
        "slippageBps": str(_settings.SWAP_SLIPPAGE_BPS),
    }
    r = httpx.get(_settings.JUPITER_QUOTE_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def swap(payer_secret: str, quote: dict) -> str:
    payer = keypair_from_secret(payer_secret)
    body = {
        "quoteResponse": quote,
        "userPublicKey": str(payer.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
    }
    r = httpx.post(_settings.JUPITER_SWAP_URL, json=body, timeout=30)
    r.raise_for_status()
    swap_tx_b64 = r.json()["swapTransaction"]

    raw = base64.b64decode(swap_tx_b64)
    unsigned = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction(unsigned.message, [payer])

    c: Client = client()
    sig = c.send_raw_transaction(
        bytes(signed),
        opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
    )
    return str(sig.value)


def swap_sol_to_asset(payer_secret: str, output_mint: str, sol_lamports: int) -> str:
    quote = get_quote(WSOL_MINT, output_mint, sol_lamports)
    return swap(payer_secret, quote)


USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def token_price_usdc(mint: str, decimals: int) -> float:
    """Best-effort USD price of one whole token, via a Jupiter quote to USDC.
    Returns 0.0 if there's no route."""
    try:
        one_token = 10 ** decimals
        q = get_quote(mint, USDC_MINT, one_token)
        out = int(q.get("outAmount", 0))
        return out / 1_000_000  # USDC has 6 decimals
    except Exception:
        return 0.0
