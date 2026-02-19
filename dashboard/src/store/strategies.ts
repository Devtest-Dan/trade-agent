import { create } from 'zustand'
import { api } from '../api/client'

interface Strategy {
  id: number
  name: string
  description: string
  autonomy: string
  enabled: boolean
  symbols: string[]
  timeframes: string[]
  created_at: string | null
  config?: any
}

interface StrategiesState {
  strategies: Strategy[]
  loading: boolean
  error: string
  fetch: () => Promise<void>
  create: (description: string) => Promise<any>
  toggle: (id: number) => Promise<void>
  setAutonomy: (id: number, autonomy: string) => Promise<void>
  remove: (id: number) => Promise<void>
}

export const useStrategiesStore = create<StrategiesState>((set, get) => ({
  strategies: [],
  loading: false,
  error: '',

  fetch: async () => {
    set({ loading: true })
    try {
      const strategies = await api.listStrategies()
      set({ strategies, loading: false, error: '' })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  create: async (description) => {
    const result = await api.createStrategy(description)
    await get().fetch()
    return result
  },

  toggle: async (id) => {
    await api.toggleStrategy(id)
    await get().fetch()
  },

  setAutonomy: async (id, autonomy) => {
    await api.setAutonomy(id, autonomy)
    await get().fetch()
  },

  remove: async (id) => {
    await api.deleteStrategy(id)
    await get().fetch()
  },
}))
