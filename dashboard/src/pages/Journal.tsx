import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp, Filter } from 'lucide-react'
import { api } from '../api/client'

interface JournalEntry {
  id: number
  trade_id: number
  playbook_db_id: number | null
  symbol: string
  direction: string
  lot_initial: number
  lot_remaining: number
  open_price: number
  close_price: number | null
  sl_initial: number | null
  tp_initial: number | null
  sl_final: number | null
  tp_final: number | null
  open_time: string | null
  close_time: string | null
  duration_seconds: number | null
  bars_held: number | null
  pnl: number | null
  pnl_pips: number | null
  rr_achieved: number | null
  outcome: string | null
  exit_reason: string | null
  playbook_phase_at_entry: string | null
  management_events_count: number
  created_at: string | null
}

interface Analytics {
  total_trades: number
  wins: number
  losses: number
  breakeven: number
  win_rate: number
  total_pnl: number
  avg_rr: number
  avg_duration_seconds: number
  profit_factor: number
}

const outcomeColors: Record<string, string> = {
  win: 'text-emerald-400',
  loss: 'text-red-400',
  breakeven: 'text-yellow-400',
}

const outcomeBg: Record<string, string> = {
  win: 'bg-emerald-500/10',
  loss: 'bg-red-500/10',
  breakeven: 'bg-yellow-500/10',
}

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<any>(null)
  const [showFilters, setShowFilters] = useState(false)

  // Filters
  const [filterSymbol, setFilterSymbol] = useState('')
  const [filterOutcome, setFilterOutcome] = useState('')
  const [filterPlaybook, setFilterPlaybook] = useState('')
  const [playbooks, setPlaybooks] = useState<any[]>([])

  useEffect(() => {
    fetchData()
    api.listPlaybooks().then(setPlaybooks).catch(() => {})
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const params: any = { limit: 100 }
      if (filterSymbol) params.symbol = filterSymbol
      if (filterOutcome) params.outcome = filterOutcome
      if (filterPlaybook) params.playbook_id = Number(filterPlaybook)

      const [entriesData, analyticsData] = await Promise.all([
        api.listJournalEntries(params),
        api.getJournalAnalytics(filterPlaybook ? { playbook_id: Number(filterPlaybook) } : {}),
      ])
      setEntries(entriesData)
      setAnalytics(analyticsData)
    } catch {
      // ignore
    }
    setLoading(false)
  }

  const handleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null)
      setExpandedDetail(null)
      return
    }
    setExpandedId(id)
    try {
      const detail = await api.getJournalEntry(id)
      setExpandedDetail(detail)
    } catch {
      setExpandedDetail(null)
    }
  }

  const applyFilters = () => {
    fetchData()
  }

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '--'
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trade Journal</h1>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
            showFilters ? 'bg-surface-raised text-content' : 'bg-surface-raised text-content-muted hover:text-content'
          }`}
        >
          <Filter size={16} /> Filters
        </button>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="bg-surface-card rounded-xl p-4 flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-xs text-content-faint block mb-1">Symbol</label>
            <input
              value={filterSymbol}
              onChange={(e) => setFilterSymbol(e.target.value)}
              placeholder="XAUUSD"
              className="px-3 py-1.5 bg-surface-inset border border-line rounded text-sm text-content w-32"
            />
          </div>
          <div>
            <label className="text-xs text-content-faint block mb-1">Outcome</label>
            <select
              value={filterOutcome}
              onChange={(e) => setFilterOutcome(e.target.value)}
              className="px-3 py-1.5 bg-surface-inset border border-line rounded text-sm text-content"
            >
              <option value="">All</option>
              <option value="win">Win</option>
              <option value="loss">Loss</option>
              <option value="breakeven">Breakeven</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-content-faint block mb-1">Playbook</label>
            <select
              value={filterPlaybook}
              onChange={(e) => setFilterPlaybook(e.target.value)}
              className="px-3 py-1.5 bg-surface-inset border border-line rounded text-sm text-content"
            >
              <option value="">All</option>
              {playbooks.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={applyFilters}
            className="px-4 py-1.5 bg-brand-600 text-white text-sm rounded hover:bg-brand-700 transition-colors"
          >
            Apply
          </button>
        </div>
      )}

      {/* Analytics summary */}
      {analytics && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard label="Total Trades" value={String(analytics.total_trades)} />
          <StatCard
            label="Win Rate"
            value={`${analytics.win_rate?.toFixed(1) || 0}%`}
            color={analytics.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}
          />
          <StatCard
            label="Total P&L"
            value={`$${analytics.total_pnl?.toFixed(2) || '0.00'}`}
            color={analytics.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}
          />
          <StatCard
            label="Avg R:R"
            value={analytics.avg_rr?.toFixed(2) || '--'}
            color="text-brand-400"
          />
          <StatCard
            label="Profit Factor"
            value={analytics.profit_factor?.toFixed(2) || '--'}
            color={analytics.profit_factor >= 1 ? 'text-emerald-400' : 'text-red-400'}
          />
        </div>
      )}

      {/* Journal table */}
      {loading ? (
        <div className="text-center py-8 text-content-faint">Loading journal...</div>
      ) : entries.length === 0 ? (
        <div className="text-center py-12 text-content-faint">
          <p>No journal entries yet.</p>
          <p className="text-sm mt-1 text-content-faint">
            Journal entries are created automatically when trades are executed through playbooks.
          </p>
        </div>
      ) : (
        <div className="bg-surface-card rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-raised/50 text-content-muted">
                <th className="px-4 py-3 text-left w-8"></th>
                <th className="px-4 py-3 text-left">Symbol</th>
                <th className="px-4 py-3 text-left">Direction</th>
                <th className="px-4 py-3 text-right">Entry</th>
                <th className="px-4 py-3 text-right">Exit</th>
                <th className="px-4 py-3 text-right">P&L</th>
                <th className="px-4 py-3 text-right">R:R</th>
                <th className="px-4 py-3 text-center">Outcome</th>
                <th className="px-4 py-3 text-right">Duration</th>
                <th className="px-4 py-3 text-left">Phase</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => (
                <>
                  <tr
                    key={entry.id}
                    onClick={() => handleExpand(entry.id)}
                    className={`border-t border-line/30 cursor-pointer hover:bg-surface-raised/30 transition-colors ${outcomeBg[entry.outcome || ''] || ''}`}
                  >
                    <td className="px-4 py-3 text-content-faint">
                      {expandedId === entry.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </td>
                    <td className="px-4 py-3 font-medium text-content">{entry.symbol}</td>
                    <td className="px-4 py-3">
                      <span className={entry.direction?.includes('BUY') || entry.direction?.includes('LONG') ? 'text-emerald-400' : 'text-red-400'}>
                        {entry.direction}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-content-secondary">{entry.open_price?.toFixed(2) || '--'}</td>
                    <td className="px-4 py-3 text-right text-content-secondary">{entry.close_price?.toFixed(2) || '--'}</td>
                    <td className={`px-4 py-3 text-right font-bold ${
                      entry.pnl !== null ? (entry.pnl >= 0 ? 'text-emerald-400' : 'text-red-400') : 'text-content-faint'
                    }`}>
                      {entry.pnl !== null ? `$${entry.pnl.toFixed(2)}` : '--'}
                    </td>
                    <td className="px-4 py-3 text-right text-content-secondary">
                      {entry.rr_achieved !== null ? `${entry.rr_achieved.toFixed(1)}R` : '--'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs font-medium ${outcomeColors[entry.outcome || ''] || 'text-content-faint'}`}>
                        {entry.outcome || 'open'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-content-muted">{formatDuration(entry.duration_seconds)}</td>
                    <td className="px-4 py-3 text-content-faint text-xs">{entry.playbook_phase_at_entry || '--'}</td>
                  </tr>

                  {/* Expanded detail row */}
                  {expandedId === entry.id && expandedDetail && (
                    <tr key={`${entry.id}-detail`} className="border-t border-line/30">
                      <td colSpan={10} className="px-6 py-4 bg-surface-raised/30">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          {/* Left: Trade details */}
                          <div className="space-y-3">
                            <h3 className="text-sm font-semibold text-content-secondary">Trade Details</h3>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div><span className="text-content-faint">Lot Initial:</span> <span className="text-content-secondary">{expandedDetail.lot_initial}</span></div>
                              <div><span className="text-content-faint">Lot Remaining:</span> <span className="text-content-secondary">{expandedDetail.lot_remaining}</span></div>
                              <div><span className="text-content-faint">SL Initial:</span> <span className="text-content-secondary">{expandedDetail.sl_initial?.toFixed(2) || '--'}</span></div>
                              <div><span className="text-content-faint">TP Initial:</span> <span className="text-content-secondary">{expandedDetail.tp_initial?.toFixed(2) || '--'}</span></div>
                              <div><span className="text-content-faint">SL Final:</span> <span className="text-content-secondary">{expandedDetail.sl_final?.toFixed(2) || '--'}</span></div>
                              <div><span className="text-content-faint">TP Final:</span> <span className="text-content-secondary">{expandedDetail.tp_final?.toFixed(2) || '--'}</span></div>
                              <div><span className="text-content-faint">Bars Held:</span> <span className="text-content-secondary">{expandedDetail.bars_held || '--'}</span></div>
                              <div><span className="text-content-faint">Exit Reason:</span> <span className="text-content-secondary">{expandedDetail.exit_reason || '--'}</span></div>
                              <div><span className="text-content-faint">P&L (pips):</span> <span className="text-content-secondary">{expandedDetail.pnl_pips?.toFixed(1) || '--'}</span></div>
                            </div>

                            {/* Management events */}
                            {expandedDetail.management_events?.length > 0 && (
                              <div>
                                <h4 className="text-xs font-semibold text-content-muted mb-1">Management Events</h4>
                                <div className="space-y-1">
                                  {expandedDetail.management_events.map((evt: any, i: number) => (
                                    <div key={i} className="text-xs bg-surface-card rounded px-2 py-1 text-content-muted">
                                      <span className="text-content-secondary">{evt.action}</span>
                                      {evt.rule && <span className="ml-2 text-content-faint">({evt.rule})</span>}
                                      {evt.details && (
                                        <span className="ml-2 text-content-faint">
                                          {Object.entries(evt.details).map(([k, v]) => `${k}=${v}`).join(', ')}
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Right: Indicator snapshots */}
                          <div className="space-y-3">
                            {expandedDetail.entry_indicators && Object.keys(expandedDetail.entry_indicators).length > 0 && (
                              <div>
                                <h3 className="text-sm font-semibold text-content-secondary mb-2">Entry Indicators</h3>
                                <div className="grid grid-cols-2 gap-1 text-xs">
                                  {Object.entries(expandedDetail.entry_indicators).map(([key, val]) => (
                                    <div key={key} className="bg-surface-card rounded px-2 py-1">
                                      <span className="text-content-faint">{key}:</span>{' '}
                                      <span className="text-content-secondary">{typeof val === 'number' ? (val as number).toFixed(4) : String(val)}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {expandedDetail.market_context && (
                              <div>
                                <h3 className="text-sm font-semibold text-content-secondary mb-2">Market Context</h3>
                                <pre className="text-[11px] text-content-muted bg-surface-card rounded p-2 overflow-auto max-h-40">
                                  {JSON.stringify(expandedDetail.market_context, null, 2)}
                                </pre>
                              </div>
                            )}

                            {expandedDetail.variables_at_entry && Object.keys(expandedDetail.variables_at_entry).length > 0 && (
                              <div>
                                <h3 className="text-sm font-semibold text-content-secondary mb-2">Playbook Variables at Entry</h3>
                                <div className="grid grid-cols-2 gap-1 text-xs">
                                  {Object.entries(expandedDetail.variables_at_entry).map(([key, val]) => (
                                    <div key={key} className="bg-surface-card rounded px-2 py-1">
                                      <span className="text-content-faint">{key}:</span>{' '}
                                      <span className="text-content-secondary">{String(val)}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color = 'text-content' }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <div className="text-xs text-content-faint mb-1">{label}</div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
    </div>
  )
}
