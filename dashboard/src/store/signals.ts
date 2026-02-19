import { create } from 'zustand'
import { api } from '../api/client'

interface Signal {
  id: number
  strategy_id: number
  strategy_name: string
  symbol: string
  direction: string
  status: string
  price_at_signal: number
  ai_reasoning: string
  conditions_snapshot: any
  created_at: string | null
}

interface SignalsState {
  signals: Signal[]
  loading: boolean
  fetch: (params?: { strategy_id?: number; status?: string }) => Promise<void>
  approve: (id: number) => Promise<void>
  reject: (id: number) => Promise<void>
  addSignal: (signal: Signal) => void
}

export const useSignalsStore = create<SignalsState>((set, get) => ({
  signals: [],
  loading: false,

  fetch: async (params) => {
    set({ loading: true })
    try {
      const signals = await api.listSignals(params)
      set({ signals, loading: false })
    } catch {
      set({ loading: false })
    }
  },

  approve: async (id) => {
    await api.approveSignal(id)
    await get().fetch()
  },

  reject: async (id) => {
    await api.rejectSignal(id)
    await get().fetch()
  },

  addSignal: (signal) => {
    set((state) => ({ signals: [signal, ...state.signals].slice(0, 100) }))
  },
}))
