"""Helius integration for fetching token holders.

Uses the Helius RPC `getTokenAccounts` method (paginated) to enumerate every
account holding the launched mint, then aggregates balances per owner. Holders
with dust below `min_raw` are skipped to avoid spraying transactions.
"""
import httpx

from config import get_settings

_settings = get_settings()


def _rpc_url() -> str:
    return f"https://mainnet.helius-rpc.com/?api-key={_settings.HELIUS_API_KEY}"


def get_holders(mint: str, min_raw: int = 1) -> dict[str, int]:
    """Return {owner_pubkey: total_raw_balance} for all holders of `mint`."""
    holders: dict[str, int] = {}
    cursor = None
    url = _rpc_url()
    with httpx.Client(timeout=60) as http:
        while True:
            params = {"mint": mint, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            body = {
                "jsonrpc": "2.0",
                "id": "voult",
                "method": "getTokenAccounts",
                "params": params,
            }
            r = http.post(url, json=body)
            r.raise_for_status()
            result = r.json().get("result", {})
            accounts = result.get("token_accounts", [])
            if not accounts:
                break
            for acc in accounts:
                owner = acc.get("owner")
                amount = int(acc.get("amount", 0))
                if owner and amount >= min_raw:
                    holders[owner] = holders.get(owner, 0) + amount
            cursor = result.get("cursor")
            if not cursor:
                break
    return holders
