import { create } from 'zustand'
import { api } from '../api/client'
import { wsClient } from '../api/ws'

interface AuthState {
  isAuthenticated: boolean
  username: string
  loading: boolean
  error: string
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: !!localStorage.getItem('token'),
  username: '',
  loading: false,
  error: '',

  login: async (username, password) => {
    set({ loading: true, error: '' })
    try {
      await api.login(username, password)
      wsClient.connect(api.getToken())
      set({ isAuthenticated: true, username, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  register: async (username, password) => {
    set({ loading: true, error: '' })
    try {
      await api.register(username, password)
      wsClient.connect(api.getToken())
      set({ isAuthenticated: true, username, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  logout: () => {
    api.clearToken()
    wsClient.disconnect()
    set({ isAuthenticated: false, username: '' })
  },

  checkAuth: () => {
    const token = api.getToken()
    if (token) {
      wsClient.connect(token)
      set({ isAuthenticated: true })
    }
  },
}))
