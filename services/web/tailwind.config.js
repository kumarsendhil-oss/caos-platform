/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      // Design B (Capacity) — the palette the customer selected in the
      // wireframes (audit-platform-wireframes-v0.2.html).
      colors: {
        teal: { DEFAULT: "#0F3D3E", dark: "#0A2C2D" },
        amber: "#E8A33D",
        slate: "#4A5A5C",
        coral: "#D65A4A",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
