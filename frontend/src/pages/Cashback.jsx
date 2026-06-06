import { useState } from "react";
import { api, getToken } from "../api";
import { Button, Panel, Label, Tag } from "../components/ui";

const PREIPO = ["SPACEX", "OPENAI", "ANTHROPIC", "ANDURIL", "KRAKEN", "NEURALINK", "DISCORD", "EPICGAMES", "FIGUREAI", "DATABRICKS", "PERPLEXITY", "XAI", "STRIPE", "KALSHI", "POLYMARKET", "RAMP"];

function fmtDuration(s) {
  if (s <= 0) return "0d";
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

export default function Cashback() {
  const authed = !!getToken();
  const [launchId, setLaunchId] = useState("");
  const [status, setStatus] = useState(null);
  const [asset, setAsset] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(null);

  async function check() {
    setErr(""); setStatus(null); setDone(null);
    if (!launchId.trim()) return;
    setBusy(true);
    try {
      setStatus(await api.cashbackStatus(launchId.trim()));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function claim() {
    setErr(""); setDone(null);
    if (!asset) return setErr("Pick an asset to receive.");
    setBusy(true);
    try {
      const res = await api.claimCashback(launchId.trim(), asset);
      setDone(res);
      setStatus(await api.cashbackStatus(launchId.trim()));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  if (!authed) {
    return (
      <div className="max-w-2xl mx-auto px-5 py-24 text-center">
        <h1 className="font-pixel text-bone text-2xl uppercase mb-4">Connect first</h1>
        <p className="text-ash text-sm">Cashback is paid to the wallet you connect with. Use Connect (top-right), then come back.</p>
      </div>
    );
  }

  const pct = status ? Math.min(100, (status.seconds_held / status.seconds_required) * 100) : 0;

  return (
    <div className="max-w-2xl mx-auto px-5 py-16">
      <h1 className="font-pixel text-bone text-2xl uppercase mb-2">Claim cashback</h1>
      <p className="text-ash text-sm mb-8">
        Hold a Voult coin long enough and your accrued cashback can be redeemed into a
        pre-IPO asset, sent straight to your wallet.
      </p>

      <Panel className="p-6 space-y-4">
        <div>
          <Label>Launch ID</Label>
          <input value={launchId} onChange={(e) => setLaunchId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && check()} placeholder="The coin's launch id" />
        </div>
        {err && <p className="text-blood text-xs">{err}</p>}
        <Button onClick={check} disabled={busy}>{busy ? "..." : "Check eligibility"}</Button>
      </Panel>

      {status && (
        <Panel className="p-6 mt-6 space-y-5 animate-rise">
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div><Label>Accrued</Label><p className="font-pixel text-gold text-lg">{status.accrued_sol.toFixed(4)} SOL</p></div>
            <div><Label>Claimed</Label><p className="text-bone">{status.claimed_sol.toFixed(4)} SOL</p></div>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <Label>Holding</Label>
              <span className="font-pixel text-[10px] text-ash">
                {fmtDuration(status.seconds_held)} / {fmtDuration(status.seconds_required)}
              </span>
            </div>
            <div className="h-3 border-2 border-line">
              <div className={`h-full ${status.eligible ? "bg-mint" : "bg-gold"}`} style={{ width: `${pct}%` }} />
            </div>
            <p className={`font-pixel text-[10px] uppercase mt-2 ${status.eligible ? "text-mint" : "text-ash"}`}>
              {status.eligible ? "✓ eligible to claim" : "not eligible yet — keep holding"}
            </p>
          </div>

          {status.eligible && status.accrued_sol > 0 && (
            <div className="pt-4 border-t-2 border-line space-y-3">
              <Label>Receive as</Label>
              <div className="flex flex-wrap gap-2">
                {PREIPO.map((s) => (
                  <button key={s} type="button" onClick={() => setAsset(s)}>
                    <Tag on={asset === s}>{s}</Tag>
                  </button>
                ))}
              </div>
              <Button className="w-full" onClick={claim} disabled={busy}>
                {busy ? "claiming..." : `Claim ${status.accrued_sol.toFixed(4)} SOL → ${asset || "?"}`}
              </Button>
            </div>
          )}

          {done && (
            <p className="text-mint text-xs break-all">
              ✓ Claimed {done.sol_spent.toFixed(4)} SOL into {done.asset}. tx: {done.tx}
            </p>
          )}
        </Panel>
      )}
    </div>
  );
}
