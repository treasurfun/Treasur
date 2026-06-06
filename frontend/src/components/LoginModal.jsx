import { useState } from "react";
import { api, setToken, getToken } from "../api";
import { Button, Label } from "./ui";

const ADJ = ["Iron", "Gold", "Neon", "Cyber", "Pixel", "Vault", "Solar", "Hyper", "Quantum", "Lunar"];
const NOUN = ["Shark", "Wolf", "Ape", "Falcon", "Tiger", "Bull", "Whale", "Phoenix", "Comet", "Raven"];

function randomName() {
  const a = ADJ[Math.floor(Math.random() * ADJ.length)];
  const n = NOUN[Math.floor(Math.random() * NOUN.length)];
  return `${a}${n}${Math.floor(Math.random() * 90 + 10)}`;
}
function randomPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%";
  return Array.from({ length: 16 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

export default function LoginModal({ open, onClose }) {
  const [mode, setMode] = useState("register"); // register | login
  const [name, setName] = useState(randomName());
  const [wallet, setWallet] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const authed = !!getToken();

  if (!open) return null;

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const { token } =
        mode === "register"
          ? await api.register(name.trim(), wallet.trim(), password)
          : await api.login(wallet.trim(), password);
      setToken(token);
      onClose(true);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken("");
    onClose(false);
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
      <div className="pixel-card shadow-pixelgold w-full max-w-md p-6 animate-rise">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-pixel text-gold text-sm uppercase">
            {authed ? "Account" : mode === "register" ? "Quick Register" : "Login"}
          </h2>
          <button onClick={() => onClose(false)} className="text-ash hover:text-bone font-pixel">[x]</button>
        </div>

        {authed ? (
          <div className="space-y-4">
            <p className="text-sm text-ash">Session active. Your launches and cashback are bound to this wallet.</p>
            <Button variant="danger" className="w-full" onClick={logout}>Disconnect</Button>
          </div>
        ) : (
          <div className="space-y-4">
            {mode === "register" && (
              <div>
                <Label>Name</Label>
                <div className="flex gap-2">
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Display name" />
                  <button type="button" onClick={() => setName(randomName())}
                    className="font-pixel text-[10px] uppercase px-3 border-2 border-line text-ash hover:border-gold hover:text-gold whitespace-nowrap">
                    random
                  </button>
                </div>
              </div>
            )}
            <div>
              <Label>Wallet</Label>
              <input value={wallet} onChange={(e) => setWallet(e.target.value)} placeholder="Your Solana wallet address..." />
            </div>
            <div>
              <Label>Password</Label>
              <div className="flex gap-2">
                <input type={mode === "register" ? "text" : "password"} value={password}
                  onChange={(e) => setPassword(e.target.value)} placeholder="Min 8 characters"
                  onKeyDown={(e) => e.key === "Enter" && submit()} />
                {mode === "register" && (
                  <button type="button" onClick={() => setPassword(randomPassword())}
                    className="font-pixel text-[10px] uppercase px-3 border-2 border-line text-ash hover:border-gold hover:text-gold whitespace-nowrap">
                    generate
                  </button>
                )}
              </div>
            </div>
            {err && <p className="text-blood text-xs">{err}</p>}
            <Button className="w-full" onClick={submit} disabled={busy}>
              {busy ? "..." : mode === "register" ? "Register" : "Login"}
            </Button>
            <p className="text-[11px] text-ash text-center">
              {mode === "register" ? "Have an account? " : "New here? "}
              <button onClick={() => { setMode(mode === "register" ? "login" : "register"); setErr(""); }}
                className="text-gold uppercase font-pixel text-[10px]">
                {mode === "register" ? "Login" : "Register"}
              </button>
            </p>
            {mode === "register" && (
              <p className="text-[10px] text-ash leading-relaxed">
                Save your password — it's hashed on the server and can't be recovered. Your wallet is your identity for launches and cashback.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
