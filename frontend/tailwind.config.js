/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        "ink-soft": "var(--ink-soft)",
        muted: "var(--muted)",
        line: "var(--line)",
        "line-soft": "var(--line-soft)",
        bg: "var(--bg)",
        card: "var(--card)",
        i9: "var(--i9)",
        "i9-dark": "var(--i9-dark)",
        "i9-tint": "var(--i9-tint)",
        gold: "var(--gold)",
        ok: "var(--ok)",
        "ok-tint": "var(--ok-tint)",
        warn: "var(--warn)",
        "warn-tint": "var(--warn-tint)",
        pend: "var(--pend)",
        "pend-tint": "var(--pend-tint)",
        field: "var(--field)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
      boxShadow: {
        DEFAULT: "var(--shadow)",
      }
    },
  },
  plugins: [],
}
