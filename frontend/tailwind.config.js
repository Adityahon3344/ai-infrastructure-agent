/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f1115",
        line: "#e6e8eb",
        panel: "#fafafa",
      },
    },
  },
  plugins: [],
};
