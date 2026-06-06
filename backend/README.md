# VOULT backend

FastAPI service that reproduces the VOULT launch engine: create a PumpFun token
with a dev buy, burn the dev allocation, swap the budget into payout assets via
Jupiter, then distribute those assets to holders over several cycles while
claiming and reinvesting PumpFun creator fees.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in values
# generate the encryption key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for the interactive API.

## Deploy (Railway or Render)

Backend needs a long-running process + a persistent disk (the orchestrator
sleeps for hours between cycles and stores encrypted keys on disk), so it can't
run on Vercel/serverless.

**Railway:** `railway.json` + `Procfile` included (Nixpacks autodetects Python).
Add a Volume mounted at `/data` and set `DATA_DIR=/data`. Set all env vars from
`.env.example` in the service variables.

**Render:** `render.yaml` included; mounts a disk at `/data`.

## Generating the metadata (Pinata)

pump.fun's old `/api/ipfs` endpoint is deprecated. Token image + metadata are
pinned to Pinata, so set `PINATA_JWT` (free key at pinata.cloud → API Keys →
copy the JWT).

## Flow

1. `POST /api/auth/login` — get a bearer token (admin if password == `ADMIN_PASSWORD`).
2. `POST /api/launches` — returns a fresh `deposit_wallet` + `required_sol`.
3. Fund that wallet with SOL.
4. `POST /api/launches/{id}/start` — kicks off the background lifecycle.
5. `GET /api/launches/{id}` — poll `status`, `cycles_done`, `distributed`.
6. `GET /api/verify/{mint}` — public check that a token came from VOULT.

## Before going live — verify these

These are the spots most likely to differ from your friend's actual setup or to
have drifted since:

- **Asset mints** (`assets.py`): 44 symbols across crypto, commodities,
  `stocks_preipo` (PreStocks) and `stocks_public` (xStocks). Most are blank. Run
  `python resolve_mints.py` to pull candidates from Jupiter's verified list, then
  confirm each on Solscan. A wrong mint loses funds.
- **PreStocks (pre-IPO)** are classic SPL on Jupiter, but jurisdiction-restricted
  (US/EU/SG excluded), need KYC for mint/redeem, and as of May 2026 the issuers
  (incl. Anthropic/OpenAI) flagged the SPV structure as possibly invalid with
  thin liquidity — holders may be unable to redeem. Weigh before distributing.
- **xStocks (public)** are Token-2022 with transfer hooks (KYC) + jurisdiction
  limits; transfers to arbitrary wallets MAY be blocked on-chain. Distribution
  auto-detects the token program, but TEST the full buy→transfer path with a tiny
  amount first.
- **Jupiter**: some stocks may not be routable for a given size; the orchestrator
  skips a failed swap leg, so check logs.
- **PumpPortal** create/claim flows verified against current docs (Pinata for
  metadata, `collectCreatorFee` claims all at once). Re-check if they change.

## Honest risk notes (read before operating)

- **Custody.** The server generates and stores each launch's private key
  (encrypted at rest with `ENCRYPTION_KEY`). Unattended multi-cycle distribution
  requires this — it can't be made non-custodial without dropping the auto-cycle
  model. Anyone with the disk + `ENCRYPTION_KEY` controls every launch wallet.
  Lock down the host accordingly.
- **Distributing tokenized stocks** (AAPL/TSLA/etc.) to holders of a token with
  an "asset-backed / auto-distribution / reinvested fees" narrative has real
  securities-law exposure in many jurisdictions. This README is not legal
  advice — get a lawyer for your jurisdiction before launching to the public.
- The simple wallet+password `login` does not verify passwords against a store;
  add a real user table before production.
