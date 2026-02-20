import { create } from 'zustand'
import { api } from '../api/client'

interface BacktestsState {
  runs: any[]
  currentResult: any | null
  loading: boolean
  error: string
  fetchRuns: (playbookId?: number) => Promise<void>
  startBacktest: (config: {
    playbook_id: number
    symbol?: string
    timeframe?: string
    bar_count?: number
    spread_pips?: number
    starting_balance?: number
  }) => Promise<any>
  fetchResult: (id: number) => Promise<void>
  deleteRun: (id: number) => Promise<void>
}

export const useBacktestsStore = create<BacktestsState>((set, get) => ({
  runs: [],
  currentResult: null,
  loading: false,
  error: '',

  fetchRuns: async (playbookId?: number) => {
    set({ loading: true, error: '' })
    try {
      const runs = await api.listBacktests({ playbook_id: playbookId, limit: 50 })
      set({ runs, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  startBacktest: async (config) => {
    set({ loading: true, error: '' })
    try {
      const result = await api.startBacktest(config)
      await get().fetchRuns()
      return result
    } catch (e: any) {
      set({ error: e.message, loading: false })
      throw e
    }
  },

  fetchResult: async (id: number) => {
    set({ loading: true, error: '' })
    try {
      const result = await api.getBacktest(id)
      set({ currentResult: result, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  deleteRun: async (id: number) => {
    try {
      await api.deleteBacktest(id)
      await get().fetchRuns()
    } catch (e: any) {
      set({ error: e.message })
    }
  },
}))
