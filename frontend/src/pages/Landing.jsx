import { Link } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { Button } from "../components/ui";
import { api } from "../api";

function VaultIcon() {
  return (
    <svg width="88" height="88" viewBox="0 0 88 88" fill="none" className="mx-auto mb-8 animate-rise" style={{ filter: "drop-shadow(0 0 18px rgba(31,157,87,0.45))" }}>
      <rect x="12" y="16" width="64" height="56" rx="4" fill="#11160f" stroke="#1f9d57" strokeWidth="3" />
      <rect x="12" y="16" width="64" height="56" rx="4" fill="none" stroke="#15803d" strokeWidth="3" strokeDasharray="2 4" opacity="0.5" />
      <circle cx="44" cy="44" r="14" fill="none" stroke="#1f9d57" strokeWidth="3" />
      <circle cx="44" cy="44" r="3.5" fill="#2bb673" />
      <line x1="44" y1="30" x2="44" y2="23" stroke="#1f9d57" strokeWidth="3" />
      <line x1="44" y1="58" x2="44" y2="65" stroke="#1f9d57" strokeWidth="3" />
      <line x1="30" y1="44" x2="23" y2="44" stroke="#1f9d57" strokeWidth="3" />
      <line x1="58" y1="44" x2="65" y2="44" stroke="#1f9d57" strokeWidth="3" />
    </svg>
  );
}

function CoinLogo({ src, sym }) {
  const [bad, setBad] = useState(false);
  if (!src || bad) {
    return (
      <div className="w-full aspect-square bg-panel2 border-b-2 border-line flex items-center justify-center font-pixel text-gold text-3xl">
        {(sym || "?").slice(0, 1)}
      </div>
    );
  }
  return <img src={src} onError={() => setBad(true)} alt="" className="w-full aspect-square object-cover border-b-2 border-line" />;
}

const FLOATING = [
  ["BTC", "8%", "12%"], ["SP500", "20%", "78%"], ["GOLD", "84%", "16%"],
  ["ETH", "92%", "62%"], ["NVDA", "6%", "52%"], ["OPENAI", "78%", "84%"],
  ["SPACEX", "50%", "6%"], ["PUMP", "94%", "38%"],
];

function short(m) {
  return m ? `${m.slice(0, 20)}…` : "";
}

export default function Landing() {
  const [feed, setFeed] = useState([]);
  const scroller = useRef(null);

  useEffect(() => {
    api.feed().then((f) => setFeed(f || [])).catch(() => {});
  }, []);

  const scroll = (d) => scroller.current?.scrollBy({ left: d * 280, behavior: "smooth" });

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden">
        {/* faint floating asset chips */}
        {FLOATING.map(([t, left, top]) => (
          <span key={t} className="hidden sm:block absolute font-pixel text-[10px] uppercase text-gold/10 select-none pointer-events-none"
            style={{ left, top }}>
            {t}
          </span>
        ))}

        <div className="max-w-4xl mx-auto px-5 pt-20 pb-16 text-center relative">
          <VaultIcon />
          <h1 className="font-pixel text-bone uppercase leading-[1.15] text-3xl sm:text-5xl lg:text-6xl">
            A coin backed by any<br />asset you want
          </h1>
          <p className="max-w-xl mx-auto text-ash text-sm sm:text-base leading-relaxed mt-7 mb-9">
            Launch on PumpFun, burn the dev buy, and distribute real crypto &amp; stock tokens to your holders automatically.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link to="/launch"><Button>Create a coin</Button></Link>
            <Link to="/verify"><Button variant="ghost">Verify a coin</Button></Link>
          </div>
        </div>
      </section>

      {/* Launched through Assetly */}
      <section className="max-w-6xl mx-auto px-5 py-10">
        <div className="font-pixel text-[10px] uppercase tracking-[0.3em] text-ash text-center mb-6">
          Launched through Assetly
        </div>

        {feed.length === 0 ? (
          <div className="text-center text-ash text-sm py-10 border-2 border-dashed border-line">
            No coins launched yet — <Link to="/launch" className="text-gold">be the first</Link>.
          </div>
        ) : (
          <div className="relative">
            <button onClick={() => scroll(-1)} aria-label="scroll left"
              className="hidden sm:flex absolute -left-3 top-1/2 -translate-y-1/2 z-10 w-9 h-9 items-center justify-center rounded-full bg-gold text-cream font-pixel">
              ‹
            </button>
            <div ref={scroller} className="flex gap-4 overflow-x-auto scroll-smooth pb-2"
              style={{ scrollbarWidth: "none" }}>
              {feed.map((c) => (
                <Link key={c.launch_id} to={`/verify?mint=${c.mint}`}
                  className="shrink-0 w-44 pixel-card hover:shadow-pixelgold transition-shadow">
                  <CoinLogo src={c.image_url} sym={c.symbol} />
                  <div className="p-3">
                    <div className="font-pixel text-[11px] uppercase text-bone truncate">{c.name}</div>
                    <div className="font-pixel text-[10px] text-gold mb-2">${c.symbol}</div>
                    <div className="text-ash text-[10px] break-all leading-tight">{short(c.mint)}</div>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {(c.assets || []).slice(0, 3).map((a) => (
                        <span key={a} className="font-pixel text-[8px] uppercase px-1.5 py-0.5 bg-panel2 border border-line text-ash">{a}</span>
                      ))}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
            <button onClick={() => scroll(1)} aria-label="scroll right"
              className="hidden sm:flex absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-9 h-9 items-center justify-center rounded-full bg-gold text-cream font-pixel">
              ›
            </button>
          </div>
        )}
      </section>

      {/* Mini how-it-works */}
      <section className="max-w-4xl mx-auto px-5 py-10">
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            ["Any asset", "Back your coin with crypto, stocks, pre-IPO, or gold."],
            ["No rug", "The dev buy is burned — zero dev supply, verifiable on-chain."],
            ["Auto payouts", "Creator fees buy your assets and pay holders every cycle."],
          ].map(([t, d]) => (
            <div key={t} className="pixel-card p-5">
              <div className="font-pixel text-gold text-xs uppercase mb-2">{t}</div>
              <p className="text-ash text-xs leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t-2 border-line mt-8">
        <div className="max-w-6xl mx-auto px-5 py-8 flex items-center justify-between flex-wrap gap-4">
          <span className="font-pixel text-bone text-sm uppercase">▦ Assetly</span>
          <div className="flex gap-5 font-pixel text-[10px] uppercase text-ash">
            <a href="#" className="hover:text-gold">X / Twitter</a>
            <a href="https://pump.fun" target="_blank" rel="noreferrer" className="hover:text-gold">Pump.fun</a>
            <a href="#" className="hover:text-gold">Github</a>
            <a href="#" className="hover:text-gold">Whitepaper</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
