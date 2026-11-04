/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'trust-navy': '#0F2444',
        'trust-green': '#1E6F43',
        'trust-canvas': '#F8FAFC',
        'trust-card': '#FFFFFF',
      },
    },
  },
  plugins: [],
}
