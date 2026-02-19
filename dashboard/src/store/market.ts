import { create } from 'zustand'
import { api } from '../api/client'

interface AccountData {
  connected: boolean
  balance: number
  equity: number
  margin: number
  free_margin: number
  profit: number
}

interface MarketState {
  account: AccountData | null
  ticks: Record<string, { bid: number; ask: number; timestamp: string }>
  settings: any
  fetchAccount: () => Promise<void>
  fetchSettings: () => Promise<void>
  updateTick: (symbol: string, bid: number, ask: number, timestamp: string) => void
}

export const useMarketStore = create<MarketState>((set) => ({
  account: null,
  ticks: {},
  settings: null,

  fetchAccount: async () => {
    try {
      const account = await api.getAccount()
      set({ account })
    } catch { /* offline */ }
  },

  fetchSettings: async () => {
    try {
      const settings = await api.getSettings()
      set({ settings })
    } catch { /* offline */ }
  },

  updateTick: (symbol, bid, ask, timestamp) => {
    set((state) => ({
      ticks: { ...state.ticks, [symbol]: { bid, ask, timestamp } },
    }))
  },
}))
