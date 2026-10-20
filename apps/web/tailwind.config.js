/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Nigeria-appropriate professional palette (deep green + naira gold,
        // kept low-saturation so it reads as a research tool, not a brand ad).
        brand: {
          50: "#eef7f1",
          100: "#d6ecdd",
          200: "#aed9bd",
          300: "#7fbf97",
          400: "#4f9f72",
          500: "#2f8258",
          600: "#1f6845",
          700: "#195337",
          800: "#16422d",
          900: "#123726",
        },
        naira: {
          50: "#fdf8e9",
          100: "#faeec4",
          200: "#f4da86",
          300: "#ecc249",
          400: "#e0aa1f",
          500: "#c08c0f",
          600: "#9a6d0b",
          700: "#73500c",
          800: "#513a0e",
          900: "#3a2a0c",
        },
        // Label colours are also exposed as CSS variables in index.css so
        // charts and inline spans can reuse the exact same values.
        "label-positive": "#059669",
        "label-negative": "#e11d48",
        "label-neutral": "#64748b",
        "label-uncertain": "#d97706",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
      },
    },
  },
  plugins: [],
};
