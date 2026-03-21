import { create } from 'zustand'
import { api } from '../api/client'

interface AnalystOpinion {
  timestamp: string
  symbol: string
  current_price: number
  bias: string
  confidence: number
  alignment: string
  trade_ideas: any[]
  changes_from_last: string
  computation_ms: number
  ai_model: string
  timeframe_analysis: Record<string, any>
  key_levels_above: any[]
  key_levels_below: any[]
  warnings: string[]
  urgency: string
  next_interval: number
  nearest_level_distance: number
  nearest_level_atr_multiple: number
  review_verdict: string
  revised_confidence: number
  review_challenges: string[]
  review_missed_risks: string[]
  review_key_concern: string
  review_recommendation: string
}

interface PerSymbolStatus {
  bias: string
  confidence: number
  urgency: string
  next_interval: number
  timestamp: string
}

interface AccuracyStat {
  stat_period: string
  total_opinions: number
  bias_accuracy: number
  avg_confidence: number
  tp1_hit_rate: number
  tp2_hit_rate: number
  sl_hit_rate: number
  avg_max_favorable: number
  avg_max_adverse: number
  level_reach_rate: number
  level_react_rate: number
  worst_bias: string
  avg_score: number
}

interface AnalystState {
  // Status
  running: boolean
  symbols: string[]
  timeframes: string[]
  model: string
  perSymbol: Record<string, PerSymbolStatus>
  totalOpinions: number

  // Current opinions
  latestOpinions: Record<string, AnalystOpinion>  // keyed by symbol
  history: AnalystOpinion[]

  // Accuracy
  accuracy: AccuracyStat[]
  scoredOpinions: any[]

  // UI state
  loading: boolean
  error: string
  selectedSymbol: string

  // Actions
  fetchStatus: () => Promise<void>
  fetchLatest: (symbol?: string) => Promise<void>
  fetchHistory: (symbol?: string) => Promise<void>
  fetchAccuracy: (symbol?: string) => Promise<void>
  fetchScored: (symbol?: string) => Promise<void>
  start: (config?: Record<string, any>) => Promise<void>
  stop: () => Promise<void>
  analyzeNow: (symbol?: string) => Promise<void>
  scoreNow: () => Promise<void>
  setSelectedSymbol: (symbol: string) => void
  handleOpinionEvent: (data: any) => void
}

export const useAnalystStore = create<AnalystState>((set, get) => ({
  running: false,
  symbols: [],
  timeframes: [],
  model: '',
  perSymbol: {},
  totalOpinions: 0,
  latestOpinions: {},
  history: [],
  accuracy: [],
  scoredOpinions: [],
  loading: false,
  error: '',
  selectedSymbol: '',

  fetchStatus: async () => {
    try {
      const data = await api.analystStatus()
      set({
        running: data.running,
        symbols: data.symbols || [],
        timeframes: data.timeframes || [],
        model: data.model || '',
        perSymbol: data.per_symbol || {},
        totalOpinions: data.total_opinions || 0,
      })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  fetchLatest: async (symbol?: string) => {
    try {
      const data = await api.analystLatest(symbol)
      if (data.symbol) {
        set((s) => ({
          latestOpinions: { ...s.latestOpinions, [data.symbol]: data },
        }))
      }
    } catch {
      // 404 = no opinion yet, not an error
    }
  },

  fetchHistory: async (symbol?: string) => {
    try {
      const data = await api.analystHistory(symbol)
      set({ history: data.opinions || [] })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  fetchAccuracy: async (symbol?: string) => {
    try {
      const data = await api.analystAccuracy(symbol || get().selectedSymbol || 'XAUUSD')
      set({ accuracy: data.stats || [] })
    } catch {
      // No stats yet
    }
  },

  fetchScored: async (symbol?: string) => {
    try {
      const data = await api.analystScored(symbol || get().selectedSymbol || 'XAUUSD')
      set({ scoredOpinions: data.opinions || [] })
    } catch {
      // No scored opinions yet
    }
  },

  start: async (config = {}) => {
    set({ loading: true, error: '' })
    try {
      await api.analystStart(config)
      await get().fetchStatus()
      set({ loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  stop: async () => {
    set({ loading: true, error: '' })
    try {
      await api.analystStop()
      set({ running: false, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  analyzeNow: async (symbol?: string) => {
    set({ loading: true, error: '' })
    try {
      const data = await api.analystAnalyze(symbol)
      // If single opinion
      if (data.symbol) {
        set((s) => ({
          latestOpinions: { ...s.latestOpinions, [data.symbol]: data },
          loading: false,
        }))
      } else if (data.opinions) {
        // Multiple opinions
        const updated: Record<string, AnalystOpinion> = { ...get().latestOpinions }
        for (const op of data.opinions) {
          updated[op.symbol] = op
        }
        set({ latestOpinions: updated, loading: false })
      }
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  scoreNow: async () => {
    try {
      await api.analystScoreNow()
      await get().fetchAccuracy()
      await get().fetchScored()
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  setSelectedSymbol: (symbol: string) => set({ selectedSymbol: symbol }),

  handleOpinionEvent: (data: any) => {
    if (data.symbol) {
      set((s) => ({
        latestOpinions: { ...s.latestOpinions, [data.symbol]: data },
        totalOpinions: s.totalOpinions + 1,
      }))
    }
  },
}))
