import { create } from 'zustand'
import { api } from '../api/client'

interface DataSummary {
  symbol: string
  timeframe: string
  bar_count: number
  first_date: string
  last_date: string
}

interface ImportJob {
  id: string
  status: string
  file_path: string
  symbol: string
  timeframe: string
  format: string
  file_size: number
  bytes_processed: number
  bars_imported: number
  started_at: string
  completed_at: string | null
  error: string | null
}

interface DataImportState {
  summary: DataSummary[]
  activeJob: ImportJob | null
  loading: boolean
  error: string
  fetchSummary: () => Promise<void>
  startImport: (config: {
    file_path: string
    symbol: string
    timeframe: string
    format?: string
    price_mode?: string
  }) => Promise<void>
  pollJob: (jobId: string) => Promise<ImportJob | null>
  cancelJob: (jobId: string) => Promise<void>
  deleteData: (symbol: string, timeframe: string) => Promise<void>
  clearJob: () => void
}

export const useDataImportStore = create<DataImportState>((set, get) => ({
  summary: [],
  activeJob: null,
  loading: false,
  error: '',

  fetchSummary: async () => {
    try {
      const data = await api.getDataSummary()
      set({ summary: data })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  startImport: async (config) => {
    set({ error: '', loading: true })
    try {
      const res = await api.startDataImport(config)
      // Start polling
      const poll = async () => {
        const job = await get().pollJob(res.job_id)
        if (job && (job.status === 'importing' || job.status === 'pending')) {
          setTimeout(poll, 2000)
        } else {
          set({ loading: false })
          get().fetchSummary()
        }
      }
      poll()
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  pollJob: async (jobId) => {
    try {
      const job = await api.getImportJob(jobId)
      set({ activeJob: job })
      return job
    } catch (e: any) {
      set({ error: e.message })
      return null
    }
  },

  cancelJob: async (jobId) => {
    try {
      await api.cancelImport(jobId)
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  deleteData: async (symbol, timeframe) => {
    try {
      await api.deleteBarData(symbol, timeframe)
      get().fetchSummary()
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  clearJob: () => set({ activeJob: null, error: '' }),
}))
