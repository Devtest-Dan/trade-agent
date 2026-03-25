import { create } from 'zustand'
import { api } from '../api/client'

export interface ActiveIndicator {
  name: string
  params: Record<string, any>
}

interface BarData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface IndicatorData {
  name: string
  params: Record<string, any>
  type: 'overlay' | 'oscillator'
  outputs: Record<string, (number | null)[]>
  markers?: { bar: number; price: number; label: string; color: string; position: 'aboveBar' | 'belowBar' }[]
}

interface ChartState {
  symbol: string
  timeframe: string
  barCount: number
  activeIndicators: ActiveIndicator[]
  bars: BarData[]
  indicatorData: Record<string, IndicatorData>
  loading: boolean
  error: string

  setSymbol: (s: string) => void
  setTimeframe: (tf: string) => void
  setBarCount: (n: number) => void
  addIndicator: (name: string, params: Record<string, any>) => void
  removeIndicator: (idx: number) => void
  fetchData: () => Promise<void>
  uploadCSV: (file: File) => Promise<number>
  updateLastBar: (symbol: string, price: number) => void
}

export const useChartStore = create<ChartState>((set, get) => ({
  symbol: localStorage.getItem('chart_symbol') || 'XAUUSD',
  timeframe: localStorage.getItem('chart_timeframe') || 'H1',
  barCount: parseInt(localStorage.getItem('chart_barCount') || '300', 10),
  activeIndicators: JSON.parse(localStorage.getItem('chart_indicators') || '[]'),
  bars: [],
  indicatorData: {},
  loading: false,
  error: '',

  setSymbol: (s) => { localStorage.setItem('chart_symbol', s); set({ symbol: s }) },
  setTimeframe: (tf) => { localStorage.setItem('chart_timeframe', tf); set({ timeframe: tf }) },
  setBarCount: (n) => { localStorage.setItem('chart_barCount', String(n)); set({ barCount: n }) },

  addIndicator: (name, params) => {
    const { activeIndicators } = get()
    const updated = [...activeIndicators, { name, params }]
    localStorage.setItem('chart_indicators', JSON.stringify(updated))
    set({ activeIndicators: updated })
  },

  removeIndicator: (idx) => {
    const { activeIndicators } = get()
    const updated = activeIndicators.filter((_, i) => i !== idx)
    localStorage.setItem('chart_indicators', JSON.stringify(updated))
    set({ activeIndicators: updated })
  },

  fetchData: async () => {
    const { symbol, timeframe, barCount, activeIndicators } = get()
    set({ loading: true, error: '' })
    try {
      const data = await api.getChartData({
        symbol,
        timeframe,
        count: barCount,
        indicators: activeIndicators,
      })
      set({ bars: data.bars, indicatorData: data.indicators, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  updateLastBar: (symbol, price) => {
    const { symbol: currentSymbol, bars } = get()
    if (symbol !== currentSymbol || bars.length === 0) return
    const lastBar = { ...bars[bars.length - 1] }
    lastBar.close = price
    if (price > lastBar.high) lastBar.high = price
    if (price < lastBar.low) lastBar.low = price
    set({ bars: [...bars.slice(0, -1), lastBar] })
  },

  uploadCSV: async (file) => {
    const { symbol, timeframe } = get()
    set({ loading: true, error: '' })
    try {
      const result = await api.uploadChartCSV(file, symbol, timeframe)
      set({ loading: false })
      return result.bars_imported
    } catch (e: any) {
      set({ error: e.message, loading: false })
      return 0
    }
  },
}))
