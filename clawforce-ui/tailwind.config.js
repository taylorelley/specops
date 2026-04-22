/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Söhne"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"Söhne Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        claude: {
          bg: "rgb(var(--claude-bg) / <alpha-value>)",
          surface: "rgb(var(--claude-surface) / <alpha-value>)",
          "surface-alt": "rgb(var(--claude-surface-alt) / <alpha-value>)",
          hover: "rgb(var(--claude-hover) / <alpha-value>)",
          border: "rgb(var(--claude-border) / <alpha-value>)",
          "border-strong": "rgb(var(--claude-border-strong) / <alpha-value>)",
          input: "rgb(var(--claude-input) / <alpha-value>)",
          "text-primary": "rgb(var(--claude-text-primary) / <alpha-value>)",
          "text-secondary": "rgb(var(--claude-text-secondary) / <alpha-value>)",
          "text-tertiary": "rgb(var(--claude-text-tertiary) / <alpha-value>)",
          "text-muted": "rgb(var(--claude-text-muted) / <alpha-value>)",
          accent: "rgb(var(--claude-accent) / <alpha-value>)",
          "accent-hover": "rgb(var(--claude-accent-hover) / <alpha-value>)",
          "accent-soft": "rgb(var(--claude-accent-soft) / <alpha-value>)",
          sidebar: "rgb(var(--claude-sidebar) / <alpha-value>)",
          "sidebar-hover": "rgb(var(--claude-sidebar-hover) / <alpha-value>)",
          "sidebar-active": "rgb(var(--claude-sidebar-active) / <alpha-value>)",
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
