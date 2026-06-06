import { useEffect, useState } from "react";
import { api, getToken } from "../api";
import { Button, Panel, Label, Tag } from "../components/ui";

const FALLBACK_ASSETS = {
  crypto: { BTC: 1, ETH: 1, ZEC: 1, PUMP: 1, HYPE: 1 },
  commodities: { GOLD: 1, SILVER: 1 },
  stocks: {
    AAPL: 1, GOOGL: 1, NVDA: 1, AMZN: 1, MSFT: 1, TSLA: 1, META: 1, NFLX: 1,
    CRM: 1, GME: 1, MSTR: 1, HOOD: 1, AVGO: 1, V: 1, CRWD: 1, CMCSA: 1,
  },
};

const STATUS_FLOW = [
  "created", "funded", "token_created", "burned", "swapped", "distributing", "complete",
];

function AssetIcon({ mint, sym, size = 20 }) {
  const [failed, setFailed] = useState(false);
  const valid = typeof mint === "string" && mint.length >= 32;
  if (failed || !valid) {
    return (
      <span
        className="inline-flex items-center justify-center rounded-full bg-goldsoft text-cream font-pixel"
        style={{ width: size, height: size, fontSize: size * 0.4 }}
      >
        {sym.slice(0, 1)}
      </span>
    );
  }
  return (
    <img
      src={`https://dd.dexscreener.com/ds-data/tokens/solana/${mint}.png?size=lg`}
      onError={() => setFailed(true)}
      alt=""
      className="rounded-full object-cover bg-panel2"
      style={{ width: size, height: size }}
    />
  );
}

function Progress({ status, cyclesDone }) {
  const idx = STATUS_FLOW.indexOf(status);
  return (
    <div className="space-y-2">
      {STATUS_FLOW.map((s, i) => {
        const done = i < idx || status === "complete";
        const active = i === idx;
        return (
          <div key={s} className="flex items-center gap-3">
            <span
              className={`w-3 h-3 border-2 ${
                done ? "bg-mint border-mint" : active ? "bg-gold border-gold animate-pulse" : "border-line"
              }`}
            />
            <span className={`font-pixel text-[11px] uppercase ${active ? "text-gold" : done ? "text-mint" : "text-ash"}`}>
              {s.replace("_", " ")}
              {s === "distributing" && cyclesDone ? ` · cycle ${cyclesDone}` : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function Launch() {
  const [authed, setAuthed] = useState(!!getToken());
  const [assets, setAssets] = useState(FALLBACK_ASSETS);
  const [cfg, setCfg] = useState({
    name: "", symbol: "", description: "", image_url: "", twitter: "", telegram: "", website: "",
  });
  const [picked, setPicked] = useState([]);
  const [weights, setWeights] = useState({}); // {sym: pct}
  const [equalSplit, setEqualSplit] = useState(true);
  const [launch, setLaunch] = useState(null); // {launch_id, deposit_wallet, required_sol, status}
  const [record, setRecord] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.assets().then(setAssets).catch(() => {});
    const onFocus = () => setAuthed(!!getToken());
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  // poll record while a launch is running
  useEffect(() => {
    if (!launch) return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api.getLaunch(launch.launch_id);
        if (!stop) setRecord(r);
      } catch {}
    };
    tick();
    const iv = setInterval(tick, 5000);
    return () => { stop = true; clearInterval(iv); };
  }, [launch]);

  const MAX_ASSETS = 3;

  function applyEqual(list) {
    const n = list.length || 1;
    const base = Math.floor((100 / n) * 10) / 10;
    const w = {};
    list.forEach((s, i) => {
      w[s] = i === n - 1 ? Math.round((100 - base * (n - 1)) * 10) / 10 : base;
    });
    return w;
  }

  function toggle(sym) {
    setPicked((p) => {
      let next;
      if (p.includes(sym)) next = p.filter((x) => x !== sym);
      else {
        if (p.length >= MAX_ASSETS) return p; // cap at 3
        next = [...p, sym];
      }
      if (equalSplit) setWeights(applyEqual(next));
      else {
        setWeights((w) => {
          const nw = {};
          next.forEach((s) => (nw[s] = w[s] ?? 0));
          return nw;
        });
      }
      return next;
    });
  }

  function setWeight(sym, val) {
    setEqualSplit(false);
    setWeights((w) => ({ ...w, [sym]: Number(val) }));
  }

  function toggleEqual() {
    setEqualSplit((e) => {
      const ne = !e;
      if (ne) setWeights(applyEqual(picked));
      return ne;
    });
  }

  const weightTotal = picked.reduce((s, k) => s + (Number(weights[k]) || 0), 0);

  async function create() {
    setErr("");
    if (!cfg.name || !cfg.symbol) return setErr("Name and symbol are required.");
    if (picked.length === 0) return setErr("Pick 1–3 payout assets.");
    if (Math.abs(weightTotal - 100) > 0.5) return setErr(`Allocations must sum to 100% (now ${weightTotal}%).`);
    setBusy(true);
    try {
      const res = await api.createLaunch({ ...cfg, payout_assets: picked, payout_weights: weights });
      setLaunch(res);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setErr("");
    setBusy(true);
    try {
      await api.startLaunch(launch.launch_id);
      const r = await api.getLaunch(launch.launch_id);
      setRecord(r);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function copy() {
    navigator.clipboard.writeText(launch.deposit_wallet);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (!authed) {
    return (
      <div className="max-w-2xl mx-auto px-5 py-24 text-center">
        <h1 className="font-pixel text-bone text-2xl uppercase mb-4">Connect first</h1>
        <p className="text-ash text-sm">Use the Connect button in the top-right to start a session, then come back.</p>
      </div>
    );
  }

  // --- Running / progress view ---
  if (launch && (record?.status && record.status !== "created")) {
    return (
      <div className="max-w-3xl mx-auto px-5 py-16">
        <h1 className="font-pixel text-bone text-2xl uppercase mb-1">{cfg.symbol || "Launch"}</h1>
        <p className="text-ash text-xs mb-8 break-all">id: {launch.launch_id}</p>

        {record.log && record.log.length > 0 && (
          <div className="terminal p-4 mb-6 text-[11px] leading-relaxed max-h-72 overflow-y-auto">
            <div className="accent mb-2">--- LAUNCHING {cfg.symbol} ---</div>
            {record.log.map((line, i) => {
              const cls = /OK$/.test(line) ? "ok" : /^\[|->/.test(line) ? "accent" : "muted";
              return <div key={i} className={cls}>{line}</div>;
            })}
            {record.status !== "complete" && record.status !== "failed" && (
              <div className="accent animate-blink">_</div>
            )}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          <Panel className="p-6">
            <Label>Progress</Label>
            <Progress status={record.status} cyclesDone={record.cycles_done} />
          </Panel>
          <Panel className="p-6 space-y-4">
            <div>
              <Label>Mint</Label>
              <p className="text-bone text-xs break-all">{record.mint || "—"}</p>
            </div>
            <div>
              <Label>Burn tx</Label>
              <p className="text-mint text-xs break-all">{record.tx_burn || "pending"}</p>
            </div>
            <div>
              <Label>Distributed (holders reached / cycle)</Label>
              <div className="flex flex-wrap gap-2">
                {Object.keys(record.distributed || {}).length === 0 && <span className="text-ash text-xs">—</span>}
                {Object.entries(record.distributed || {}).map(([k, v]) => (
                  <span key={k} className="font-pixel text-[10px] px-2 py-1 border-2 border-line text-gold">
                    {k}:{v}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <Label>Fees claimed</Label>
              <p className="text-bone text-xs">{(record.fees_claimed_sol || 0).toFixed(4)} SOL</p>
            </div>
            {record.error && <p className="text-blood text-xs break-all">{record.error}</p>}
          </Panel>
        </div>
      </div>
    );
  }

  // --- Funding step ---
  if (launch) {
    return (
      <div className="max-w-2xl mx-auto px-5 py-16">
        <h1 className="font-pixel text-bone text-2xl uppercase mb-6">Fund the launch wallet</h1>
        <Panel className="p-6 space-y-5">
          <div>
            <Label>Send exactly ≥ this much SOL</Label>
            <p className="font-pixel text-gold text-2xl">{launch.required_sol} SOL</p>
          </div>
          <div>
            <Label>Deposit wallet</Label>
            <div className="flex items-center gap-2">
              <code className="text-bone text-xs break-all flex-1 border-2 border-line p-2">{launch.deposit_wallet}</code>
              <Button variant="ghost" onClick={copy}>{copied ? "ok" : "copy"}</Button>
            </div>
          </div>
          <p className="text-ash text-xs leading-relaxed">
            This is a freshly generated wallet dedicated to this launch. Once it's funded, hit
            Start — the backend creates the token, burns the dev buy, swaps into your assets,
            and begins distribution cycles.
          </p>
          {err && <p className="text-blood text-xs">{err}</p>}
          <Button className="w-full" onClick={start} disabled={busy}>
            {busy ? "starting..." : "I've funded it — Start"}
          </Button>
        </Panel>
      </div>
    );
  }

  // --- Config step ---
  return (
    <div className="max-w-3xl mx-auto px-5 py-12">
      <h1 className="font-pixel text-bone text-2xl uppercase mb-1">New launch</h1>
      <p className="text-ash text-sm mb-8">Configure your token, then pick the assets your holders will receive.</p>

      <Panel className="p-6 space-y-5 mb-6">
        <div className="grid sm:grid-cols-2 gap-5">
          <div>
            <Label>Name *</Label>
            <input value={cfg.name} onChange={(e) => setCfg({ ...cfg, name: e.target.value })} placeholder="Voult Gold" />
          </div>
          <div>
            <Label>Symbol *</Label>
            <input value={cfg.symbol} onChange={(e) => setCfg({ ...cfg, symbol: e.target.value })} placeholder="VGOLD" />
          </div>
        </div>
        <div>
          <Label>Description</Label>
          <textarea rows={3} value={cfg.description} onChange={(e) => setCfg({ ...cfg, description: e.target.value })} />
        </div>
        <div className="grid sm:grid-cols-2 gap-5">
          <div><Label>Image URL</Label><input value={cfg.image_url} onChange={(e) => setCfg({ ...cfg, image_url: e.target.value })} placeholder="https://..." /></div>
          <div><Label>Website</Label><input value={cfg.website} onChange={(e) => setCfg({ ...cfg, website: e.target.value })} /></div>
          <div><Label>Twitter</Label><input value={cfg.twitter} onChange={(e) => setCfg({ ...cfg, twitter: e.target.value })} /></div>
          <div><Label>Telegram</Label><input value={cfg.telegram} onChange={(e) => setCfg({ ...cfg, telegram: e.target.value })} /></div>
        </div>
      </Panel>

      <Panel className="p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <Label>Pick assets (max 3)</Label>
          <button
            type="button"
            onClick={toggleEqual}
            className={`font-pixel text-[9px] uppercase tracking-widest px-2 py-1 border-2 ${
              equalSplit ? "border-gold text-gold" : "border-line text-ash"
            }`}
          >
            equal split
          </button>
        </div>
        {Object.entries(assets).map(([group, items]) => {
          const syms = Object.keys(items).filter((s) => !!items[s]); // only assets with a mint
          if (syms.length === 0) return null;
          return (
            <div key={group} className="mb-5">
              <div className="font-pixel text-[9px] uppercase tracking-widest text-ash mb-2">{group.replace("_", " ")}</div>
              <div className="flex flex-wrap gap-2">
                {syms.map((sym) => {
                  const on = picked.includes(sym);
                  const full = !on && picked.length >= MAX_ASSETS;
                  return (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => toggle(sym)}
                      disabled={full}
                      className={`flex items-center gap-2 px-3 py-2 border-2 rounded font-pixel text-[10px] uppercase transition-colors
                        ${on ? "border-gold bg-gold text-cream shadow-pixelgold" : "border-line bg-panel2 text-ash"}
                        ${full ? "opacity-30 cursor-not-allowed" : "hover:border-gold hover:text-gold"}`}
                    >
                      <AssetIcon mint={items[sym]} sym={sym} />
                      {sym}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {picked.length > 0 && (
          <div className="mt-6 pt-5 border-t-2 border-line space-y-4">
            <div className="flex items-center justify-between">
              <Label>Allocation</Label>
              <span className={`font-pixel text-[10px] ${Math.abs(weightTotal - 100) > 0.5 ? "text-blood" : "text-mint"}`}>
                {weightTotal}%
              </span>
            </div>
            {picked.map((sym) => (
              <div key={sym} className="flex items-center gap-3">
                <span className="font-pixel text-[11px] text-bone w-16">{sym}</span>
                <input
                  type="range" min="0" max="100" step="0.1"
                  value={weights[sym] ?? 0}
                  onChange={(e) => setWeight(sym, e.target.value)}
                  className="flex-1 accent-gold"
                  style={{ width: "auto", padding: 0, border: "none", background: "transparent" }}
                />
                <span className="font-pixel text-[11px] text-gold w-14 text-right">{(weights[sym] ?? 0).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        )}
        <p className="text-ash text-[11px] mt-3">{picked.length}/3 selected</p>
      </Panel>

      {err && <p className="text-blood text-sm mb-4">{err}</p>}
      <Button onClick={create} disabled={busy}>{busy ? "creating..." : "Create launch →"}</Button>
    </div>
  );
}
