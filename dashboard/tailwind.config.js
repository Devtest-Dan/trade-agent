/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#b9dffe',
          300: '#7cc4fd',
          400: '#36a6fa',
          500: '#0c8aeb',
          600: '#006dc9',
          700: '#0157a3',
          800: '#064a86',
          900: '#0b3f6f',
        },
      },
    },
  },
  plugins: [],
}
