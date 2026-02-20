import { create } from 'zustand'

interface ThemeState {
  dark: boolean
  toggle: () => void
}

function applyTheme(dark: boolean) {
  if (dark) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

const saved = localStorage.getItem('theme')
const prefersDark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
applyTheme(prefersDark)

export const useThemeStore = create<ThemeState>((set) => ({
  dark: prefersDark,
  toggle: () =>
    set((state) => {
      const next = !state.dark
      applyTheme(next)
      localStorage.setItem('theme', next ? 'dark' : 'light')
      return { dark: next }
    }),
}))
