const BASE_URL = '/api'

class ApiClient {
  private token: string = ''

  setToken(token: string) {
    this.token = token
    localStorage.setItem('token', token)
  }

  getToken(): string {
    if (!this.token) {
      this.token = localStorage.getItem('token') || ''
    }
    return this.token
  }

  clearToken() {
    this.token = ''
    localStorage.removeItem('token')
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    }
    const token = this.getToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

    if (res.status === 401) {
      this.clearToken()
      throw new Error('Unauthorized')
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'Request failed')
    }

    return res.json()
  }

  // Auth
  async login(username: string, password: string) {
    const data = await this.request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    this.setToken(data.access_token)
    return data
  }

  async register(username: string, password: string) {
    const data = await this.request<{ access_token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    this.setToken(data.access_token)
    return data
  }

  // Health
  async health() {
    return this.request<{ status: string; mt5_connected: boolean; kill_switch: boolean }>('/health')
  }

  // Strategies
  async createStrategy(description: string) {
    return this.request<any>('/strategies', {
      method: 'POST',
      body: JSON.stringify({ description }),
    })
  }

  async listStrategies() {
    return this.request<any[]>('/strategies')
  }

  async getStrategy(id: number) {
    return this.request<any>(`/strategies/${id}`)
  }

  async updateStrategy(id: number, data: any) {
    return this.request<any>(`/strategies/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async deleteStrategy(id: number) {
    return this.request<any>(`/strategies/${id}`, { method: 'DELETE' })
  }

  async setAutonomy(id: number, autonomy: string) {
    return this.request<any>(`/strategies/${id}/autonomy`, {
      method: 'PUT',
      body: JSON.stringify({ autonomy }),
    })
  }

  async toggleStrategy(id: number) {
    return this.request<any>(`/strategies/${id}/toggle`, { method: 'PUT' })
  }

  async chatWithStrategy(id: number, messages: { role: string; content: string }[]) {
    return this.request<{ reply: string }>(`/strategies/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ messages }),
    })
  }

  // Signals
  async listSignals(params?: { strategy_id?: number; status?: string; limit?: number }) {
    const qs = new URLSearchParams()
    if (params?.strategy_id) qs.set('strategy_id', String(params.strategy_id))
    if (params?.status) qs.set('status', params.status)
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs}` : ''
    return this.request<any[]>(`/signals${query}`)
  }

  async approveSignal(id: number) {
    return this.request<any>(`/signals/${id}/approve`, { method: 'POST' })
  }

  async rejectSignal(id: number) {
    return this.request<any>(`/signals/${id}/reject`, { method: 'POST' })
  }

  // Trades
  async listTrades(params?: { strategy_id?: number; symbol?: string; limit?: number }) {
    const qs = new URLSearchParams()
    if (params?.strategy_id) qs.set('strategy_id', String(params.strategy_id))
    if (params?.symbol) qs.set('symbol', params.symbol)
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs}` : ''
    return this.request<any[]>(`/trades${query}`)
  }

  async getOpenPositions() {
    return this.request<any[]>('/trades/open')
  }

  // Market
  async getMarketData(symbol: string) {
    return this.request<any>(`/market/${symbol}`)
  }

  async getAccount() {
    return this.request<any>('/account')
  }

  async getIndicators() {
    return this.request<any[]>('/indicators')
  }

  // Settings
  async getSettings() {
    return this.request<any>('/settings')
  }

  async updateSettings(data: any) {
    return this.request<any>('/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async killSwitch() {
    return this.request<any>('/kill-switch', { method: 'POST' })
  }

  async deactivateKillSwitch() {
    return this.request<any>('/kill-switch/deactivate', { method: 'POST' })
  }
}

export const api = new ApiClient()
