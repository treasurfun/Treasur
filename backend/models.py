"""Request/response and internal data models."""
import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LaunchStatus(str, Enum):
    CREATED = "created"            # config saved, awaiting funding
    FUNDED = "funded"             # wallet has SOL
    TOKEN_CREATED = "token_created"
    BURNED = "burned"
    SWAPPED = "swapped"
    DISTRIBUTING = "distributing"
    COMPLETE = "complete"
    FAILED = "failed"


class TokenConfig(BaseModel):
    name: str = Field(..., max_length=64)
    symbol: str = Field(..., max_length=10)
    description: str = Field("", max_length=500)
    image_url: Optional[str] = None
    # base64 data-URL of an uploaded/drag-dropped image (preferred over image_url)
    image_data: Optional[str] = None
    twitter: Optional[str] = None
    telegram: Optional[str] = None
    website: Optional[str] = None
    # which assets to buy and distribute, e.g. ["BTC", "AAPL"] (max 3)
    payout_assets: list[str] = Field(default_factory=list)
    # optional per-asset split in percent, e.g. {"BTC": 50, "ETH": 50}.
    # empty => equal split across payout_assets.
    payout_weights: dict[str, float] = Field(default_factory=dict)


class CreateLaunchRequest(BaseModel):
    config: TokenConfig


class CreateLaunchResponse(BaseModel):
    launch_id: str
    deposit_wallet: str
    required_sol: float
    status: LaunchStatus


class HolderState(BaseModel):
    first_seen: Optional[float] = None   # epoch seconds of (continuous) holding start
    last_seen: float = 0
    balance: int = 0                     # last observed raw token balance
    accrued_lamports: int = 0            # cashback accrued, in SOL lamports
    claimed_lamports: int = 0            # cashback already claimed


class LaunchRecord(BaseModel):
    launch_id: str
    owner: str                       # wallet address of the user who created it
    created_at: float = Field(default_factory=time.time)
    config: TokenConfig
    deposit_wallet: str              # public key of the fresh launch wallet
    encrypted_secret: str            # Fernet-encrypted base58 secret key
    status: LaunchStatus = LaunchStatus.CREATED
    mint: Optional[str] = None
    tx_create: Optional[str] = None
    tx_burn: Optional[str] = None
    cycles_done: int = 0
    distributed: dict = Field(default_factory=dict)   # symbol -> total raw amount sent
    fees_claimed_sol: float = 0.0
    cashback_pool_lamports: int = 0                   # total fees routed to holders
    treasury_sent_lamports: int = 0                   # cumulative SOL (raw) sent to treasury (the 20% share)
    treasury_sent_usd: float = 0.0                    # cumulative USD value of treasury cuts (captured at transfer)
    holders: dict[str, HolderState] = Field(default_factory=dict)
    log: list[str] = Field(default_factory=list)      # live launch console lines
    error: Optional[str] = None


class CashbackStatus(BaseModel):
    wallet: str
    balance: int
    eligible: bool
    accrued_sol: float
    claimed_sol: float
    seconds_held: float
    seconds_required: float


class ClaimRequest(BaseModel):
    asset: str                       # which PreStock/asset to receive


class ClaimResponse(BaseModel):
    tx: str
    asset: str
    sol_spent: float


class VerifyResponse(BaseModel):
    is_treasur: bool
    mint: str
    launch_id: Optional[str] = None
    status: Optional[str] = None
    burned: bool = False
    distributed: dict = Field(default_factory=dict)
