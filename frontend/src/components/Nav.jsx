import { Link, useLocation } from "react-router-dom";
import { getToken } from "../api";

export default function Nav({ onLogin }) {
  const loc = useLocation();
  const authed = !!getToken();
  const link = (to, label) => {
    const active = loc.pathname === to;
    return (
      <Link
        to={to}
        className={`font-pixel text-[11px] uppercase tracking-wide px-2 py-1 ${
          active ? "text-gold" : "text-ash hover:text-bone"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="border-b-2 border-line bg-panel/85 backdrop-blur sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <span className="font-pixel text-gold text-base">▦</span>
          <span className="font-pixel text-bone text-xl tracking-tight">ASSETLY</span>
          <span className="hidden sm:inline w-2 h-4 bg-gold animate-blink" />
        </Link>
        <nav className="flex items-center gap-3 sm:gap-5">
          {link("/launch", "Launch")}
          {link("/cashback", "Cashback")}
          {link("/profile", "Profile")}
          {link("/verify", "Verify")}
          <Link
            to="/launch"
            className="hidden sm:inline-block font-pixel text-[11px] uppercase tracking-wide px-3 py-2 bg-gold text-cream shadow-pixelgold hover:bg-goldsoft"
          >
            Create coin
          </Link>
          <button
            onClick={onLogin}
            className="font-pixel text-[11px] uppercase tracking-wide px-3 py-2 border-2 border-line text-bone hover:border-gold hover:text-gold"
          >
            {authed ? "Account" : "Quick login"}
          </button>
        </nav>
      </div>
    </header>
  );
}
