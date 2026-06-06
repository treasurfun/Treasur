import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken } from "../api";
import { Button, Panel, Label, Tag } from "../components/ui";

const STATUS_COLOR = {
  complete: "text-mint",
  distributing: "text-gold",
  failed: "text-blood",
};

function short(addr) {
  return addr ? `${addr.slice(0, 4)}…${addr.slice(-4)}` : "—";
}

export default function Profile() {
  const authed = !!getToken();
  const [me, setMe] = useState(null);
  const [launches, setLaunches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!authed) { setLoading(false); return; }
    Promise.all([api.me().catch(() => null), api.myLaunches().catch(() => [])])
      .then(([m, l]) => { setMe(m); setLaunches(l || []); })
      .finally(() => setLoading(false));
  }, [authed]);

  if (!authed) {
    return (
      <div className="max-w-2xl mx-auto px-5 py-24 text-center">
        <h1 className="font-pixel text-bone text-2xl uppercase mb-4">Connect first</h1>
        <p className="text-ash text-sm">Use Connect (top-right) to view your profile.</p>
      </div>
    );
  }

  function copy() {
    if (me?.wallet) {
      navigator.clipboard.writeText(me.wallet);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }

  const totalFees = launches.reduce((s, l) => s + (l.fees_claimed_sol || 0), 0);

  return (
    <div className="max-w-3xl mx-auto px-5 py-16">
      <h1 className="font-pixel text-bone text-2xl uppercase mb-6">Profile</h1>

      <Panel className="p-6 mb-6">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <Label>Name</Label>
            <p className="font-pixel text-gold text-lg">{me?.name || "—"}</p>
          </div>
          <div className="text-right">
            <Label>Wallet</Label>
            <button onClick={copy} className="text-bone text-sm hover:text-gold">
              {short(me?.wallet)} {copied ? "✓" : "⧉"}
            </button>
          </div>
        </div>
        {me?.admin && <p className="font-pixel text-[10px] uppercase text-blood mt-3">admin</p>}
      </Panel>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <Panel className="p-5">
          <Label>Coins launched</Label>
          <p className="font-pixel text-bone text-2xl">{launches.length}</p>
        </Panel>
        <Panel className="p-5">
          <Label>Total fees claimed</Label>
          <p className="font-pixel text-bone text-2xl">{totalFees.toFixed(3)} SOL</p>
        </Panel>
      </div>

      <div className="flex items-center justify-between mb-3">
        <Label>My coins</Label>
        <Link to="/launch"><Button variant="ghost">+ New</Button></Link>
      </div>

      {loading ? (
        <p className="text-ash text-sm">Loading…</p>
      ) : launches.length === 0 ? (
        <Panel className="p-6 text-center">
          <p className="text-ash text-sm mb-4">No coins yet.</p>
          <Link to="/launch"><Button>Launch your first coin</Button></Link>
        </Panel>
      ) : (
        <div className="space-y-3">
          {launches.map((l) => (
            <Panel key={l.launch_id} className="p-5">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <p className="font-pixel text-bone text-sm uppercase">
                    {l.config?.symbol || "—"} <span className="text-ash">/ {l.config?.name}</span>
                  </p>
                  <p className="text-ash text-[11px] break-all mt-1">{short(l.mint)} · id {l.launch_id}</p>
                </div>
                <span className={`font-pixel text-[10px] uppercase ${STATUS_COLOR[l.status] || "text-ash"}`}>
                  {String(l.status).replace("_", " ")}
                </span>
              </div>
              <div className="flex flex-wrap gap-2 mb-3">
                {(l.config?.payout_assets || []).map((a) => <Tag key={a} on>{a}</Tag>)}
              </div>
              <div className="flex gap-5 text-[11px] text-ash">
                <span>cycles: <span className="text-bone">{l.cycles_done || 0}</span></span>
                <span>fees: <span className="text-bone">{(l.fees_claimed_sol || 0).toFixed(3)} SOL</span></span>
                {l.mint && (
                  <a className="text-gold ml-auto" href={`https://pump.fun/coin/${l.mint}`} target="_blank" rel="noreferrer">
                    view on pump.fun ↗
                  </a>
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
