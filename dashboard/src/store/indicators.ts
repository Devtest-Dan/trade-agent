import { create } from 'zustand'
import { api } from '../api/client'

interface IndicatorsState {
  indicators: any[]
  loading: boolean
  error: string
  uploadJob: { id: string; status: string; error: string | null; result_name: string | null } | null
  fetchIndicators: () => Promise<void>
  uploadIndicator: (file: File, name?: string) => Promise<string>
  pollJob: (jobId: string) => Promise<void>
  deleteIndicator: (name: string) => Promise<void>
  clearJob: () => void
}

export const useIndicatorsStore = create<IndicatorsState>((set, get) => ({
  indicators: [],
  loading: false,
  error: '',
  uploadJob: null,

  fetchIndicators: async () => {
    set({ loading: true, error: '' })
    try {
      const indicators = await api.listIndicators()
      set({ indicators, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  uploadIndicator: async (file: File, name?: string) => {
    set({ error: '' })
    try {
      const result = await api.uploadIndicator(file, name)
      set({ uploadJob: { id: result.job_id, status: result.status, error: null, result_name: null } })
      return result.job_id
    } catch (e: any) {
      set({ error: e.message })
      throw e
    }
  },

  pollJob: async (jobId: string) => {
    try {
      const job = await api.getIndicatorJob(jobId)
      set({
        uploadJob: {
          id: job.id,
          status: job.status,
          error: job.error,
          result_name: job.result_name,
        },
      })
      if (job.status === 'complete') {
        await get().fetchIndicators()
      }
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  deleteIndicator: async (name: string) => {
    try {
      await api.deleteIndicator(name)
      await get().fetchIndicators()
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  clearJob: () => set({ uploadJob: null }),
}))
