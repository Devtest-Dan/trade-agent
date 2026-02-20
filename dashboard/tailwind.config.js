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
        surface: {
          page: 'rgb(var(--s-page) / <alpha-value>)',
          card: 'rgb(var(--s-card) / <alpha-value>)',
          raised: 'rgb(var(--s-raised) / <alpha-value>)',
          inset: 'rgb(var(--s-inset) / <alpha-value>)',
          nav: 'rgb(var(--s-nav) / <alpha-value>)',
        },
        line: {
          DEFAULT: 'rgb(var(--line) / <alpha-value>)',
        },
        content: {
          DEFAULT: 'rgb(var(--c-primary) / <alpha-value>)',
          secondary: 'rgb(var(--c-secondary) / <alpha-value>)',
          muted: 'rgb(var(--c-muted) / <alpha-value>)',
          faint: 'rgb(var(--c-faint) / <alpha-value>)',
          inverse: 'rgb(var(--c-inverse) / <alpha-value>)',
        },
      },
      borderRadius: {
        xl: '0.75rem',
      },
    },
  },
  plugins: [],
}
