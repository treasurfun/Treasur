# VOULT

Asset-backed token launcher on Solana. Launch a PumpFun token, burn the dev buy
(zero dev allocation), then route creator fees to holders as a loyalty
**cashback**: the longer someone holds, the more they accrue, and they can redeem
it into a pre-IPO asset (PreStocks) sent to their own wallet. A legacy "auto"
mode that buys assets and sprays them to all holders each cycle is also available
(`DISTRIBUTION_MODE`).

```
frontend/   React 19 + Vite + Tailwind  → Netlify (drag dist/)
backend/    FastAPI + Solana            → Render (persistent disk at /data)
```

## Quick start

1. **Backend** — see `backend/README.md`. Fill `.env`, generate `ENCRYPTION_KEY`,
   `uvicorn main:app --port 8000`.
2. **Frontend** — see `frontend/README.md`. `npm install && npm run dev`.
   For production, point `frontend/public/_redirects` at your backend URL.

## Architecture

```
Frontend (Netlify) ──/api/*──▶ Backend (FastAPI, Render)
                                  ├─ PumpFun (PumpPortal)  create + claim fees
                                  ├─ Jupiter v6            SOL → assets swaps
                                  ├─ Helius                holder enumeration
                                  └─ Solana RPC            keypair / burn / transfer
```

## Before going live — checklist

- Fill real SPL mints in `backend/assets.py` (only BTC/ETH stubbed).
- Verify the PumpFun/PumpPortal endpoint shapes in `backend/services/pumpfun.py`.
- Set a strong `ADMIN_PASSWORD`, a random `SECRET_KEY`, and a real Fernet
  `ENCRYPTION_KEY`; lock down the host that holds the data disk.
- Auth: users register with name + wallet + password (PBKDF2-hashed, stored in
  `DATA_DIR/users.json`); login verifies the hash. Set a strong `ADMIN_PASSWORD`.

## Honest risk notes

- **Custody:** the backend holds each launch's private key (encrypted at rest).
  The unattended multi-cycle distribution model requires this — it can't be made
  non-custodial without dropping auto-cycles. Whoever controls the disk +
  `ENCRYPTION_KEY` controls every launch wallet.
- **Tokenized stocks:** distributing AAPL/TSLA-style tokens to holders under an
  "asset-backed / auto-distribution / reinvested fees" narrative carries real
  securities-law exposure in many jurisdictions. Not legal advice — consult a
  lawyer for yours before launching publicly.

License: MIT
