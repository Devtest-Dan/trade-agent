const NGROK_URL = 'https://decoctive-semipalmate-brian.ngrok-free.dev'
const isLocalhost = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
const BASE_URL = isLocalhost ? '/api' : `${NGROK_URL}/api`

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
      'ngrok-skip-browser-warning': '1',
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

  async testAI() {
    return this.request<any>('/settings/test-ai', { method: 'POST' })
  }

  // Playbooks
  async buildPlaybook(description: string) {
    return this.request<any>('/playbooks', {
      method: 'POST',
      body: JSON.stringify({ description }),
    })
  }

  async listPlaybooks() {
    return this.request<any[]>('/playbooks')
  }

  async getPlaybook(id: number) {
    return this.request<any>(`/playbooks/${id}`)
  }

  async updatePlaybook(id: number, data: any) {
    return this.request<any>(`/playbooks/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async deletePlaybook(id: number) {
    return this.request<any>(`/playbooks/${id}`, { method: 'DELETE' })
  }

  async togglePlaybook(id: number) {
    return this.request<any>(`/playbooks/${id}/toggle`, { method: 'PUT' })
  }

  async refinePlaybook(id: number, messages: { role: string; content: string }[]) {
    return this.request<any>(`/playbooks/${id}/refine`, {
      method: 'POST',
      body: JSON.stringify({ messages }),
    })
  }

  async refineFromBacktest(id: number, backtestId: number, messages: { role: string; content: string }[]) {
    return this.request<any>(`/playbooks/${id}/refine-from-backtest`, {
      method: 'POST',
      body: JSON.stringify({ backtest_id: backtestId, messages }),
    })
  }

  async createShadow(id: number) {
    return this.request<{ id: number; shadow_of: number; name: string }>(`/playbooks/${id}/shadow`, {
      method: 'POST',
    })
  }

  async promoteShadow(id: number) {
    return this.request<{ status: string; parent_id: number }>(`/playbooks/${id}/shadow/promote`, {
      method: 'POST',
    })
  }

  async getCircuitBreaker(id: number) {
    return this.request<{
      active: boolean
      consecutive_losses: number
      error_count: number
      tripped: boolean
      tripped_at: string | null
      config: { max_consecutive_losses: number; max_errors: number; cooldown_minutes: number }
    }>(`/playbooks/${id}/circuit-breaker`)
  }

  async resetCircuitBreaker(id: number) {
    return this.request<{ status: string }>(`/playbooks/${id}/circuit-breaker/reset`, {
      method: 'POST',
    })
  }

  async getPlaybookRefinements(id: number) {
    return this.request<any[]>(`/playbooks/${id}/refinements`)
  }

  async getPlaybookVersions(id: number) {
    return this.request<any>(`/playbooks/${id}/versions`)
  }

  async rollbackPlaybook(id: number, version: number) {
    return this.request<any>(`/playbooks/${id}/rollback/${version}`, { method: 'POST' })
  }

  async getPlaybookState(id: number) {
    return this.request<any>(`/playbooks/${id}/state`)
  }

  // Journal
  async listJournalEntries(params?: {
    playbook_id?: number
    strategy_id?: number
    symbol?: string
    outcome?: string
    limit?: number
    offset?: number
  }) {
    const qs = new URLSearchParams()
    if (params?.playbook_id) qs.set('playbook_id', String(params.playbook_id))
    if (params?.strategy_id) qs.set('strategy_id', String(params.strategy_id))
    if (params?.symbol) qs.set('symbol', params.symbol)
    if (params?.outcome) qs.set('outcome', params.outcome)
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    const query = qs.toString() ? `?${qs}` : ''
    return this.request<any[]>(`/journal${query}`)
  }

  async getJournalEntry(id: number) {
    return this.request<any>(`/journal/${id}`)
  }

  async getJournalAnalytics(params?: {
    playbook_id?: number
    strategy_id?: number
    symbol?: string
  }) {
    const qs = new URLSearchParams()
    if (params?.playbook_id) qs.set('playbook_id', String(params.playbook_id))
    if (params?.strategy_id) qs.set('strategy_id', String(params.strategy_id))
    if (params?.symbol) qs.set('symbol', params.symbol)
    const query = qs.toString() ? `?${qs}` : ''
    return this.request<any>(`/journal/analytics${query}`)
  }

  async getConditionAnalytics(playbookId?: number) {
    const qs = playbookId ? `?playbook_id=${playbookId}` : ''
    return this.request<any[]>(`/journal/analytics/conditions${qs}`)
  }
  // Indicators
  async listIndicators() {
    return this.request<any[]>('/indicators')
  }

  async uploadIndicator(file: File, name?: string) {
    const formData = new FormData()
    formData.append('file', file)
    if (name) formData.append('name', name)

    const token = this.getToken()
    const headers: Record<string, string> = {
      'ngrok-skip-browser-warning': '1',
    }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${BASE_URL}/indicators/upload`, {
      method: 'POST',
      headers,
      body: formData,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'Upload failed')
    }
    return res.json() as Promise<{ job_id: string; status: string; indicator_name: string }>
  }

  async getIndicatorJob(jobId: string) {
    return this.request<{
      id: string
      status: string
      indicator_name: string | null
      error: string | null
      result_name: string | null
    }>(`/indicators/jobs/${jobId}`)
  }

  async getIndicatorDetail(name: string) {
    return this.request<any>(`/indicators/${name}`)
  }

  async getIndicatorCode(name: string) {
    return this.request<{ name: string; compute_py: string | null; source_mq5: string | null }>(
      `/indicators/${name}/code`
    )
  }

  async updateIndicatorCode(name: string, computePy: string) {
    return this.request<{ status: string; name: string }>(`/indicators/${name}/code`, {
      method: 'PUT',
      body: JSON.stringify({ compute_py: computePy }),
    })
  }

  async deleteIndicator(name: string) {
    return this.request<{ status: string; name: string }>(`/indicators/${name}`, {
      method: 'DELETE',
    })
  }

  // Chart
  async getChartData(req: {
    symbol: string
    timeframe: string
    count: number
    indicators: { name: string; params: Record<string, any> }[]
  }) {
    return this.request<{
      symbol: string
      timeframe: string
      bars: { time: number; open: number; high: number; low: number; close: number; volume: number }[]
      indicators: Record<
        string,
        {
          name: string
          params: Record<string, any>
          type: 'overlay' | 'oscillator'
          outputs: Record<string, (number | null)[]>
          markers?: { bar: number; price: number; label: string; color: string; position: 'aboveBar' | 'belowBar' }[]
        }
      >
    }>('/chart/data', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async uploadChartCSV(file: File, symbol: string, timeframe: string) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('symbol', symbol)
    formData.append('timeframe', timeframe)

    const token = this.getToken()
    const headers: Record<string, string> = {
      'ngrok-skip-browser-warning': '1',
    }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${BASE_URL}/chart/upload`, {
      method: 'POST',
      headers,
      body: formData,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'Upload failed')
    }
    return res.json() as Promise<{ bars_imported: number; symbol: string; timeframe: string }>
  }

  // Backtests
  async startBacktest(config: {
    playbook_id: number
    symbol?: string
    timeframe?: string
    bar_count?: number
    spread_pips?: number
    slippage_pips?: number
    commission_per_lot?: number
    starting_balance?: number
    start_date?: string | null
    end_date?: string | null
  }) {
    return this.request<any>('/backtests', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  }

  async listBacktests(params?: { playbook_id?: number; limit?: number }) {
    const qs = new URLSearchParams()
    if (params?.playbook_id) qs.set('playbook_id', String(params.playbook_id))
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs}` : ''
    return this.request<any[]>(`/backtests${query}`)
  }

  async getBacktest(id: number) {
    return this.request<any>(`/backtests/${id}`)
  }

  async deleteBacktest(id: number) {
    return this.request<any>(`/backtests/${id}`, { method: 'DELETE' })
  }

  async getComboAnalytics(backtestId: number) {
    return this.request<any>(`/backtests/${backtestId}/combo-analytics`)
  }

  async getRegimeBreakdown(backtestId: number) {
    return this.request<any>(`/backtests/${backtestId}/regime-breakdown`)
  }

  async getHypotheses(backtestId: number) {
    return this.request<{
      run_id: number
      count: number
      hypotheses: {
        category: string
        observation: string
        suggestion: string
        confidence: string
        param_path: string | null
        current_value: number | null
        suggested_value: number | null
      }[]
    }>(`/backtests/${backtestId}/hypotheses`)
  }

  async compareBacktests(ids: number[]) {
    return this.request<any>(`/backtests/compare?ids=${ids.join(',')}`)
  }

  async runMonteCarlo(backtestId: number, iterations: number = 1000) {
    return this.request<any>(`/backtests/${backtestId}/monte-carlo`, {
      method: 'POST',
      body: JSON.stringify({ backtest_id: backtestId, iterations }),
    })
  }

  async runWalkForward(config: {
    playbook_id: number
    symbol?: string
    timeframe?: string
    bar_count?: number
    spread_pips?: number
    slippage_pips?: number
    commission_per_lot?: number
    starting_balance?: number
    in_sample_bars?: number
    out_of_sample_bars?: number
    step_bars?: number
  }) {
    return this.request<any>('/backtests/walk-forward', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  }

  async startSweep(config: {
    playbook_id: number
    symbol?: string
    timeframe?: string
    bar_count?: number
    spread_pips?: number
    slippage_pips?: number
    commission_per_lot?: number
    starting_balance?: number
    params: { path: string; values: number[] }[]
    rank_by?: string
  }) {
    return this.request<any>('/backtests/sweep', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  }

  getExportCsvUrl(backtestId: number): string {
    return `${BASE_URL}/backtests/${backtestId}/export-csv`
  }

  async fetchBars(symbol: string, timeframe: string, count: number) {
    return this.request<any>('/backtests/fetch-bars', {
      method: 'POST',
      body: JSON.stringify({ symbol, timeframe, count }),
    })
  }

  // Data Import
  async startDataImport(config: {
    file_path: string
    symbol: string
    timeframe: string
    format?: string
    price_mode?: string
  }) {
    return this.request<{ job_id: string; status: string }>('/data/import', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  }

  async getImportJob(jobId: string) {
    return this.request<{
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
    }>(`/data/import/${jobId}`)
  }

  async cancelImport(jobId: string) {
    return this.request<{ status: string }>(`/data/import/${jobId}/cancel`, {
      method: 'POST',
    })
  }

  async listImports() {
    return this.request<any[]>('/data/imports')
  }

  async getDataSummary() {
    return this.request<{
      symbol: string
      timeframe: string
      bar_count: number
      first_date: string
      last_date: string
    }[]>('/data/summary')
  }

  async deleteBarData(symbol: string, timeframe: string) {
    return this.request<{ deleted: number; symbol: string; timeframe: string }>(
      `/data/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
      { method: 'DELETE' }
    )
  }

  // Knowledge / Skill Graph
  async listSkills(params?: {
    category?: string
    confidence?: string
    symbol?: string
    playbook_id?: number
    market_regime?: string
    source_type?: string
    search?: string
    limit?: number
    offset?: number
  }) {
    const qs = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
      })
    }
    const query = qs.toString()
    return this.request<any[]>(`/knowledge/skills${query ? '?' + query : ''}`)
  }

  async getSkill(id: number) {
    return this.request<any>(`/knowledge/skills/${id}`)
  }

  async createSkill(data: any) {
    return this.request<any>('/knowledge/skills', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateSkill(id: number, data: any) {
    return this.request<any>(`/knowledge/skills/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async deleteSkill(id: number) {
    return this.request<{ deleted: boolean }>(`/knowledge/skills/${id}`, {
      method: 'DELETE',
    })
  }

  async getSkillGraph(id: number, depth: number = 2) {
    return this.request<{ nodes: any[]; edges: any[] }>(
      `/knowledge/skills/${id}/graph?depth=${depth}`
    )
  }

  async extractSkills(backtestId: number) {
    return this.request<{ nodes_created: number; edges_created: number; nodes: any[] }>(
      `/knowledge/extract/${backtestId}`,
      { method: 'POST' }
    )
  }

  async deleteExtractedSkills(backtestId: number) {
    return this.request<{ deleted: number }>(
      `/knowledge/extract/${backtestId}`,
      { method: 'DELETE' }
    )
  }

  async getFullGraph() {
    return this.request<{ nodes: any[]; edges: any[] }>('/knowledge/graph')
  }

  async getKnowledgeStats() {
    return this.request<{
      total: number
      by_confidence: { HIGH: number; MEDIUM: number; LOW: number }
      by_category: Record<string, number>
    }>('/knowledge/stats')
  }
}

export const api = new ApiClient()
