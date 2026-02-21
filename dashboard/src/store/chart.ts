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
}

export const useChartStore = create<ChartState>((set, get) => ({
  symbol: 'XAUUSD',
  timeframe: 'H1',
  barCount: 300,
  activeIndicators: [],
  bars: [],
  indicatorData: {},
  loading: false,
  error: '',

  setSymbol: (s) => set({ symbol: s }),
  setTimeframe: (tf) => set({ timeframe: tf }),
  setBarCount: (n) => set({ barCount: n }),

  addIndicator: (name, params) => {
    const { activeIndicators } = get()
    set({ activeIndicators: [...activeIndicators, { name, params }] })
  },

  removeIndicator: (idx) => {
    const { activeIndicators } = get()
    set({ activeIndicators: activeIndicators.filter((_, i) => i !== idx) })
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
