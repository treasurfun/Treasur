// Small set of blocky pixel-styled UI primitives.

export function Button({ children, variant = "gold", className = "", ...props }) {
  const base =
    "font-pixel text-[11px] uppercase tracking-wide px-5 py-3 border-2 transition-all active:translate-x-[2px] active:translate-y-[2px] disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    gold: "bg-gold text-ink border-black shadow-pixel hover:bg-goldsoft",
    ghost: "bg-transparent text-bone border-line hover:border-gold hover:text-gold shadow-pixel",
    danger: "bg-blood text-ink border-black shadow-pixel hover:opacity-90",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Panel({ children, className = "" }) {
  return <div className={`pixel-card shadow-pixel ${className}`}>{children}</div>;
}

export function Label({ children }) {
  return (
    <div className="font-pixel text-[10px] uppercase tracking-widest text-ash mb-2">
      {children}
    </div>
  );
}

export function Tag({ children, on }) {
  return (
    <span
      className={`font-pixel text-[9px] uppercase px-2 py-1 border-2 ${
        on ? "border-gold text-gold" : "border-line text-ash"
      }`}
    >
      {children}
    </span>
  );
}
