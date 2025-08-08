/******** Tailwind CSS config (Next 12) ********/
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./app/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        chatgpt: {
          "primary": "#16a085",
          "secondary": "#1f2937",
          "accent": "#34d399",
          "neutral": "#111827",
          "base-100": "#0b0f16",
          "info": "#38bdf8",
          "success": "#34d399",
          "warning": "#f59e0b",
          "error": "#ef4444",
        },
      },
      "dark",
    ],
    darkTheme: "chatgpt",
  },
};
