import { create } from 'zustand'
import { api } from '../api/client'

interface Playbook {
  id: number
  name: string
  description_nl: string
  autonomy: string
  enabled: boolean
  symbols: string[]
  phases: string[]
  created_at: string | null
  updated_at: string | null
}

interface PlaybooksState {
  playbooks: Playbook[]
  loading: boolean
  error: string
  fetch: () => Promise<void>
  build: (description: string) => Promise<any>
  toggle: (id: number) => Promise<void>
  remove: (id: number) => Promise<void>
}

export const usePlaybooksStore = create<PlaybooksState>((set, get) => ({
  playbooks: [],
  loading: false,
  error: '',

  fetch: async () => {
    set({ loading: true })
    try {
      const playbooks = await api.listPlaybooks()
      set({ playbooks, loading: false, error: '' })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  build: async (description) => {
    const result = await api.buildPlaybook(description)
    await get().fetch()
    return result
  },

  toggle: async (id) => {
    await api.togglePlaybook(id)
    await get().fetch()
  },

  remove: async (id) => {
    await api.deletePlaybook(id)
    await get().fetch()
  },
}))
