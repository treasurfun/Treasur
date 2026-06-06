/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#e6ece7",      // light body text (token name kept)
        cream: "#0a0e0c",    // near-black background
        panel: "#11160f",    // dark card
        panel2: "#161c14",
        line: "#243029",     // dark borders
        gold: "#1f9d57",     // green accent (token name kept for compatibility)
        goldsoft: "#15803d",
        mint: "#2bb673",
        ash: "#8b988c",      // muted gray-green
        bone: "#f2f7f2",     // primary light text
        blood: "#e0544a",
      },
      fontFamily: {
        pixel: ['"Silkscreen"', "monospace"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        pixel: "4px 4px 0 0 #241f18",
        pixelgold: "4px 4px 0 0 #1f9d57",
      },
      keyframes: {
        flicker: {
          "0%,100%": { opacity: "1" },
          "92%": { opacity: "1" },
          "94%": { opacity: "0.6" },
          "96%": { opacity: "1" },
        },
        rise: {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: { "0%,49%": { opacity: "1" }, "50%,100%": { opacity: "0" } },
      },
      animation: {
        flicker: "flicker 6s infinite",
        rise: "rise 0.6s ease-out both",
        blink: "blink 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
