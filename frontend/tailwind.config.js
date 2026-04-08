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
        vercel: {
          "primary": "#ffffff",        // White accent (Vercel style)
          "primary-content": "#000000",
          "secondary": "#333333",
          "accent": "#0070f3",         // Vercel blue for links/highlights
          "neutral": "#111111",
          "neutral-content": "#ededed",
          "base-100": "#000000",       // Pure black background
          "base-200": "#0a0a0a",       // Near-black
          "base-300": "#111111",       // Subtle border/elevated
          "base-content": "#ededed",   // Light gray text
          "info": "#0070f3",
          "success": "#0070f3",
          "warning": "#f5a623",
          "error": "#ee0000",
        },
      },
    ],
    darkTheme: "vercel",
  },
};
