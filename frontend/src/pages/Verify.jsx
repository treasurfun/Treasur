import { useState } from "react";
import { api } from "../api";
import { Button, Panel, Label } from "../components/ui";

export default function Verify() {
  const [mint, setMint] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function check() {
    setErr(""); setRes(null);
    if (!mint.trim()) return;
    setBusy(true);
    try {
      setRes(await api.verify(mint.trim()));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-5 py-16">
      <h1 className="font-pixel text-bone text-2xl uppercase mb-2">Verify a coin</h1>
      <p className="text-ash text-sm mb-8">
        Paste a token's contract address to check whether it was launched through VOULT.
      </p>

      <Panel className="p-6 space-y-4">
        <div>
          <Label>Mint / contract address</Label>
          <input
            value={mint}
            onChange={(e) => setMint(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && check()}
            placeholder="e.g. CDsN...pump"
          />
        </div>
        {err && <p className="text-blood text-xs">{err}</p>}
        <Button onClick={check} disabled={busy}>{busy ? "checking..." : "Verify"}</Button>
      </Panel>

      {res && (
        <Panel className={`p-6 mt-6 animate-rise border-2 ${res.is_voult ? "!border-mint" : "!border-blood"}`}>
          <div className={`font-pixel text-sm uppercase mb-4 ${res.is_voult ? "text-mint" : "text-blood"}`}>
            {res.is_voult ? "✓ Launched through VOULT" : "✗ Not a VOULT token"}
          </div>
          {res.is_voult && (
            <div className="space-y-3 text-xs">
              <Row k="Status" v={res.status} />
              <Row k="Dev buy burned" v={res.burned ? "yes" : "no"} accent={res.burned} />
              <Row k="Launch ID" v={res.launch_id} />
              <div>
                <Label>Distributed</Label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(res.distributed || {}).map(([k, v]) => (
                    <span key={k} className="font-pixel text-[10px] px-2 py-1 border-2 border-line text-gold">{k}:{v}</span>
                  ))}
                  {Object.keys(res.distributed || {}).length === 0 && <span className="text-ash">—</span>}
                </div>
              </div>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}

function Row({ k, v, accent }) {
  return (
    <div className="flex justify-between gap-4 border-b-2 border-line pb-2">
      <span className="text-ash uppercase font-pixel text-[10px]">{k}</span>
      <span className={`break-all ${accent ? "text-mint" : "text-bone"}`}>{v || "—"}</span>
    </div>
  );
}
