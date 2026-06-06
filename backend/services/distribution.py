"""Distribution: send payout-asset tokens to holders proportional to holdings.

Allocation is pro-rata by token balance (a simple, transparent tier rule). The
launch wallet must already hold the payout assets (bought via Jupiter) and
enough SOL to fund recipient ATAs + fees.
"""
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.message import MessageV0
from solders.transaction import VersionedTransaction

from spl.token.instructions import (
    get_associated_token_address,
    create_associated_token_account,
    transfer_checked,
    TransferCheckedParams,
)
from spl.token.constants import TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID

from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from services.solana_client import keypair_from_secret, client, get_token_balance_raw


def _mint_info(c, mint: str):
    """Return (decimals, token_program_id) for a mint, supporting Token-2022."""
    info = c.get_account_info_json_parsed(Pubkey.from_string(mint)).value
    decimals = info.data.parsed["info"]["decimals"]
    program_id = info.owner  # the program that owns the mint (classic or 2022)
    return decimals, program_id


def _mint_decimals(c, mint: str) -> int:
    return _mint_info(c, mint)[0]


def transfer_token_to(launch_secret: str, asset_mint: str, to_wallet: str, raw_amount: int) -> str:
    """Send `raw_amount` of `asset_mint` from the launch wallet to one recipient,
    creating their ATA if needed. Supports classic SPL and Token-2022."""
    c = client()
    payer = keypair_from_secret(launch_secret)
    decimals, program_id = _mint_info(c, asset_mint)
    mint_pk = Pubkey.from_string(asset_mint)
    owner_pk = Pubkey.from_string(to_wallet)
    src_ata = get_associated_token_address(payer.pubkey(), mint_pk, program_id)
    dst_ata = get_associated_token_address(owner_pk, mint_pk, program_id)

    ixs = []
    if c.get_account_info(dst_ata).value is None:
        ixs.append(create_associated_token_account(payer.pubkey(), owner_pk, mint_pk, program_id))
    ixs.append(
        transfer_checked(
            TransferCheckedParams(
                program_id=program_id, source=src_ata, mint=mint_pk, dest=dst_ata,
                owner=payer.pubkey(), amount=raw_amount, decimals=decimals, signers=[],
            )
        )
    )
    bh = c.get_latest_blockhash().value.blockhash
    msg = MessageV0.try_compile(payer.pubkey(), ixs, [], bh)
    tx = VersionedTransaction(msg, [payer])
    sig = c.send_transaction(tx, opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed))
    return str(sig.value)


def distribute_asset(
    launch_secret: str,
    asset_mint: str,
    holders: dict[str, int],
    exclude: set[str] | None = None,
) -> dict[str, str]:
    """Distribute the launch wallet's full balance of `asset_mint` to holders
    pro-rata. Returns {holder: tx_signature}. Sends in small batches."""
    exclude = exclude or set()
    c = client()
    payer = keypair_from_secret(launch_secret)
    payer_pk = str(payer.pubkey())

    holders = {h: b for h, b in holders.items() if h not in exclude and h != payer_pk}
    total_weight = sum(holders.values())
    if total_weight == 0:
        return {}

    decimals, program_id = _mint_info(c, asset_mint)
    pool = get_token_balance_raw(payer_pk, asset_mint, program_id)
    if pool == 0:
        return {}

    mint_pk = Pubkey.from_string(asset_mint)
    src_ata = get_associated_token_address(payer.pubkey(), mint_pk, program_id)

    results: dict[str, str] = {}
    batch: list = []
    batch_holders: list[str] = []

    def flush():
        nonlocal batch, batch_holders
        if not batch:
            return
        bh = c.get_latest_blockhash().value.blockhash
        msg = MessageV0.try_compile(payer.pubkey(), batch, [], bh)
        tx = VersionedTransaction(msg, [payer])
        sig = c.send_transaction(
            tx, opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
        )
        for h in batch_holders:
            results[h] = str(sig.value)
        batch, batch_holders = [], []

    for holder, weight in holders.items():
        amount = pool * weight // total_weight
        if amount <= 0:
            continue
        owner_pk = Pubkey.from_string(holder)
        dst_ata = get_associated_token_address(owner_pk, mint_pk, program_id)
        ixs = []
        if c.get_account_info(dst_ata).value is None:
            ixs.append(
                create_associated_token_account(payer.pubkey(), owner_pk, mint_pk, program_id)
            )
        ixs.append(
            transfer_checked(
                TransferCheckedParams(
                    program_id=program_id,
                    source=src_ata,
                    mint=mint_pk,
                    dest=dst_ata,
                    owner=payer.pubkey(),
                    amount=amount,
                    decimals=decimals,
                    signers=[],
                )
            )
        )
        # ~5 transfers (with ATA creation) per tx to stay under size limits
        if len(batch) + len(ixs) > 10:
            flush()
        batch.extend(ixs)
        batch_holders.append(holder)

    flush()
    return results
