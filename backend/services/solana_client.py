"""Solana on-chain helpers built on solders + solana-py.

Covers: fresh keypair generation, SOL balance checks, SOL transfers, and the
SPL burn used to zero out the dev-buy allocation.
"""
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from solders.message import MessageV0

from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from spl.token.instructions import burn, BurnParams, get_associated_token_address
from spl.token.constants import TOKEN_PROGRAM_ID

from config import get_settings

_settings = get_settings()
LAMPORTS_PER_SOL = 1_000_000_000


def client() -> Client:
    return Client(_settings.RPC_ENDPOINT, commitment=Confirmed)


def new_wallet() -> tuple[str, str]:
    """Return (pubkey_str, secret_base58)."""
    kp = Keypair()
    return str(kp.pubkey()), str(kp)  # str(Keypair) is the base58 secret


def keypair_from_secret(secret_b58: str) -> Keypair:
    return Keypair.from_base58_string(secret_b58)


def get_balance_sol(pubkey: str) -> float:
    lamports = client().get_balance(Pubkey.from_string(pubkey)).value
    return lamports / LAMPORTS_PER_SOL


def _send_v0(c: Client, payer: Keypair, instructions: list) -> str:
    bh = c.get_latest_blockhash().value.blockhash
    msg = MessageV0.try_compile(payer.pubkey(), instructions, [], bh)
    tx = VersionedTransaction(msg, [payer])
    sig = c.send_transaction(tx, opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed))
    return str(sig.value)


def transfer_sol(from_secret: str, to_pubkey: str, sol: float) -> str:
    c = client()
    payer = keypair_from_secret(from_secret)
    ix = transfer(
        TransferParams(
            from_pubkey=payer.pubkey(),
            to_pubkey=Pubkey.from_string(to_pubkey),
            lamports=int(sol * LAMPORTS_PER_SOL),
        )
    )
    return _send_v0(c, payer, [ix])


def burn_all(owner_secret: str, mint: str, decimals: int, raw_amount: int) -> str:
    """Burn `raw_amount` of `mint` held by owner's associated token account."""
    c = client()
    owner = keypair_from_secret(owner_secret)
    ata = get_associated_token_address(owner.pubkey(), Pubkey.from_string(mint))
    ix = burn(
        BurnParams(
            program_id=TOKEN_PROGRAM_ID,
            account=ata,
            mint=Pubkey.from_string(mint),
            owner=owner.pubkey(),
            amount=raw_amount,
            signers=[],
        )
    )
    return _send_v0(c, owner, [ix])


def get_token_balance_raw(owner_pubkey: str, mint: str, program_id=None) -> int:
    c = client()
    pid = program_id or TOKEN_PROGRAM_ID
    ata = get_associated_token_address(
        Pubkey.from_string(owner_pubkey), Pubkey.from_string(mint), pid
    )
    resp = c.get_token_account_balance(ata)
    try:
        return int(resp.value.amount)
    except Exception:
        return 0
