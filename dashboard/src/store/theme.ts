import { create } from 'zustand'

interface ThemeColors {
  lightPage: string
  lightCard: string
  darkPage: string
  darkCard: string
}

interface ThemeState {
  dark: boolean
  colors: ThemeColors
  toggle: () => void
  setColors: (colors: Partial<ThemeColors>) => void
  resetColors: () => void
}

const DEFAULT_COLORS: ThemeColors = {
  lightPage: '#ffffff',
  lightCard: '#dcfce7',
  darkPage: '#080c1c',
  darkCard: '#1e284b',
}

function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `${r} ${g} ${b}`
}

function applyTheme(dark: boolean, colors: ThemeColors) {
  const root = document.documentElement
  if (dark) {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
  // Apply custom colors as CSS variables
  root.style.setProperty('--custom-light-page', hexToRgb(colors.lightPage))
  root.style.setProperty('--custom-light-card', colors.lightCard)
  root.style.setProperty('--custom-dark-page', hexToRgb(colors.darkPage))
  root.style.setProperty('--custom-dark-card', colors.darkCard)
}

function loadColors(): ThemeColors {
  try {
    const raw = localStorage.getItem('theme-colors')
    if (raw) return { ...DEFAULT_COLORS, ...JSON.parse(raw) }
  } catch {}
  return DEFAULT_COLORS
}

const saved = localStorage.getItem('theme')
const prefersDark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
const initialColors = loadColors()
applyTheme(prefersDark, initialColors)

export const useThemeStore = create<ThemeState>((set, get) => ({
  dark: prefersDark,
  colors: initialColors,
  toggle: () =>
    set((state) => {
      const next = !state.dark
      applyTheme(next, state.colors)
      localStorage.setItem('theme', next ? 'dark' : 'light')
      return { dark: next }
    }),
  setColors: (partial) =>
    set((state) => {
      const colors = { ...state.colors, ...partial }
      applyTheme(state.dark, colors)
      localStorage.setItem('theme-colors', JSON.stringify(colors))
      return { colors }
    }),
  resetColors: () =>
    set((state) => {
      applyTheme(state.dark, DEFAULT_COLORS)
      localStorage.removeItem('theme-colors')
      return { colors: DEFAULT_COLORS }
    }),
}))

export { DEFAULT_COLORS }
