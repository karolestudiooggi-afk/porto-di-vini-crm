import type { Config } from "tailwindcss";

/**
 * Design system Domani — reconstruído a partir do app.css/input.css originais.
 * Cores de tema (app/surface/panel/ink/muted/line) usam canais RGB em CSS vars,
 * permitindo opacidade nativa do Tailwind: bg-surface, text-ink/60, border-line/12...
 */
const withVar = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // tokens reativos ao tema (claro/escuro)
        app: withVar("--app"),
        surface: withVar("--surface"),
        panel: withVar("--panel"),
        ink: withVar("--ink"),
        muted: withVar("--muted"),
        line: withVar("--line"),
        // marca (fixas)
        domani: {
          orange: "#E56D23",
          "orange-300": "#F0A074",
          "orange-600": "#C85A18",
          graphite: "#1D1D1F",
          slate: "#2A2A2E",
          ink: "#0E0E10",
          mist: "#F5F3EF",
          line: "#1D1D1F",
        },
      },
      fontFamily: {
        display: ["Sora", "Hanken Grotesk", "sans-serif"],
        sans: ["Hanken Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        "4xl": "2rem",
      },
      boxShadow: {
        "domani-lift":
          "0 1px 2px rgba(14,14,16,.04), 0 8px 24px -12px rgba(14,14,16,.12)",
        "domani-card": "0 24px 60px -12px rgba(0,0,0,.45)",
      },
      keyframes: {
        "domani-fade": { from: { opacity: "0" }, to: { opacity: "1" } },
        "domani-drawer": {
          from: { transform: "translateX(24px)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
        "domani-pop": {
          from: { transform: "translateY(8px) scale(0.98)", opacity: "0" },
          to: { transform: "translateY(0) scale(1)", opacity: "1" },
        },
        "domani-rise": {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "overlay-fade": "domani-fade .18s ease-out",
        "drawer-panel": "domani-drawer .24s cubic-bezier(.22,1,.36,1)",
        "modal-panel": "domani-pop .2s cubic-bezier(.22,1,.36,1)",
        "rise": "domani-rise .55s cubic-bezier(.22,1,.36,1) both",
      },
    },
  },
  plugins: [],
};

export default config;
