import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FlaskConical, Play, Trash2, Download, Eye, Upload, X, Database, GitBranch, Plus, Minus, Loader2 } from 'lucide-react'
import { useBacktestsStore } from '../store/backtests'
import { usePlaybooksStore } from '../store/playbooks'
import { useDataImportStore } from '../store/dataImport'
import { api } from '../api/client'

const SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'GBPJPY', 'EURJPY']
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
const FORMATS = ['auto', 'tick_csv', 'bar_csv', 'hst']
const PRICE_MODES = ['bid', 'mid', 'ask']

export default function Backtest() {
  const navigate = useNavigate()
  const { runs, loading, error, fetchRuns, startBacktest, deleteRun } = useBacktestsStore()
  const { playbooks, fetch: fetchPlaybooks } = usePlaybooksStore()
  const {
    summary, activeJob, loading: importing, error: importError,
    fetchSummary, startImport, cancelJob, deleteData, clearJob,
  } = useDataImportStore()

  const [playbookId, setPlaybookId] = useState<number>(0)
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('H4')
  const [barCount, setBarCount] = useState(500)
  const [spreadPips, setSpreadPips] = useState(0.3)
  const [startingBalance, setStartingBalance] = useState(10000)
  const [running, setRunning] = useState(false)
  const [fetchingBars, setFetchingBars] = useState(false)
  const [fetchMsg, setFetchMsg] = useState('')
  const [compareIds, setCompareIds] = useState<number[]>([])
  const [compareResult, setCompareResult] = useState<any>(null)
  const [comparing, setComparing] = useState(false)

  const toggleCompare = (id: number) => {
    setCompareIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const handleCompare = async () => {
    if (compareIds.length < 2) return
    setComparing(true)
    try {
      const res = await api.compareBacktests(compareIds)
      setCompareResult(res)
    } catch (e: any) {
      // handle error
    }
    setComparing(false)
  }

  // Sweep state
  const [sweepOpen, setSweepOpen] = useState(false)
  const [sweepParams, setSweepParams] = useState<{ path: string; values: string }[]>([
    { path: '', values: '' },
  ])
  const [sweepRankBy, setSweepRankBy] = useState('sharpe_ratio')
  const [sweepRunning, setSweepRunning] = useState(false)
  const [sweepResult, setSweepResult] = useState<any>(null)
  const [sweepError, setSweepError] = useState('')

  const handleSweep = async () => {
    if (!playbookId) return
    const params = sweepParams
      .filter(p => p.path.trim() && p.values.trim())
      .map(p => ({
        path: p.path.trim(),
        values: p.values.split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v)),
      }))
      .filter(p => p.values.length >= 2)
    if (params.length === 0) {
      setSweepError('Add at least one parameter with 2+ values')
      return
    }
    setSweepRunning(true)
    setSweepError('')
    setSweepResult(null)
    try {
      const res = await api.startSweep({
        playbook_id: playbookId,
        symbol,
        timeframe,
        bar_count: barCount,
        spread_pips: spreadPips,
        starting_balance: startingBalance,
        params,
        rank_by: sweepRankBy,
      })
      setSweepResult(res)
    } catch (e: any) {
      setSweepError(e.message)
    }
    setSweepRunning(false)
  }

  // Import form state
  const [importPath, setImportPath] = useState('')
  const [importSymbol, setImportSymbol] = useState('XAUUSD')
  const [importTf, setImportTf] = useState('H1')
  const [importFormat, setImportFormat] = useState('auto')
  const [importPriceMode, setImportPriceMode] = useState('bid')

  useEffect(() => {
    fetchPlaybooks()
    fetchRuns()
    fetchSummary()
  }, [])

  const handleRun = async () => {
    if (!playbookId) return
    setRunning(true)
    try {
      const result = await startBacktest({
        playbook_id: playbookId,
        symbol,
        timeframe,
        bar_count: barCount,
        spread_pips: spreadPips,
        starting_balance: startingBalance,
      })
      if (result?.id) {
        navigate(`/backtest/${result.id}`)
      }
    } catch (e: any) {
      // error is in store
    }
    setRunning(false)
  }

  const handleFetchBars = async () => {
    setFetchingBars(true)
    setFetchMsg('')
    try {
      const res = await api.fetchBars(symbol, timeframe, barCount)
      setFetchMsg(`Fetched ${res.fetched} bars (${res.total_cached} total cached)`)
    } catch (e: any) {
      setFetchMsg(`Failed: ${e.message}`)
    }
    setFetchingBars(false)
  }

  const handleStartImport = () => {
    if (!importPath.trim()) return
    startImport({
      file_path: importPath.trim(),
      symbol: importSymbol,
      timeframe: importTf,
      format: importFormat,
      price_mode: importPriceMode,
    })
  }

  const progress = activeJob
    ? activeJob.file_size > 0
      ? Math.min(100, Math.round((activeJob.bytes_processed / activeJob.file_size) * 100))
      : 0
    : 0

  const formatBytes = (bytes: number) => {
    if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
    if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(0)} KB`
    return `${bytes} B`
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <FlaskConical size={24} className="text-brand-400" />
        <h1 className="text-2xl font-bold">Backtest</h1>
      </div>

      {/* Config Form */}
      <div className="bg-surface-card rounded-xl p-6">
        <h2 className="text-lg font-semibold text-content mb-4">Configuration</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-content-muted mb-1">Playbook</label>
            <select
              value={playbookId}
              onChange={e => setPlaybookId(Number(e.target.value))}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
            >
              <option value={0}>Select playbook...</option>
              {playbooks.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Symbol</label>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
            >
              {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
            >
              {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Bar Count</label>
            <input
              type="number"
              value={barCount}
              onChange={e => setBarCount(Number(e.target.value))}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
              min={60}
              max={5000}
            />
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Spread (pips)</label>
            <input
              type="number"
              value={spreadPips}
              onChange={e => setSpreadPips(Number(e.target.value))}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
              step={0.1}
              min={0}
            />
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Starting Balance ($)</label>
            <input
              type="number"
              value={startingBalance}
              onChange={e => setStartingBalance(Number(e.target.value))}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
              step={1000}
              min={100}
            />
          </div>
        </div>

        <div className="flex gap-3 mt-5">
          <button
            onClick={handleRun}
            disabled={!playbookId || running}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
          >
            <Play size={16} />
            {running ? 'Running...' : 'Run Backtest'}
          </button>
          <button
            onClick={handleFetchBars}
            disabled={fetchingBars}
            className="flex items-center gap-2 px-5 py-2.5 bg-surface-raised hover:bg-surface-raised disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
          >
            <Download size={16} />
            {fetchingBars ? 'Fetching...' : 'Fetch Bars from MT5'}
          </button>
        </div>

        {fetchMsg && <p className="mt-2 text-sm text-content-muted">{fetchMsg}</p>}
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </div>

      {/* Parameter Sweep */}
      <div className="bg-surface-card rounded-xl overflow-hidden">
        <button
          onClick={() => setSweepOpen(!sweepOpen)}
          className="w-full px-6 py-4 flex items-center gap-2 hover:bg-surface-raised/30 transition-colors"
        >
          <GitBranch size={18} className="text-brand-400" />
          <h2 className="text-lg font-semibold text-content">Parameter Sweep</h2>
          <span className="text-content-faint text-sm ml-2">Test multiple parameter combinations</span>
          <span className="ml-auto text-content-muted">{sweepOpen ? '-' : '+'}</span>
        </button>

        {sweepOpen && (
          <div className="px-6 pb-6 space-y-4 border-t border-line/30 pt-4">
            <p className="text-sm text-content-muted">
              Sweep playbook variables, risk settings, or spread. Use paths like <code className="text-brand-400">variables.rsi_threshold</code>, <code className="text-brand-400">risk.max_lot</code>, <code className="text-brand-400">spread_pips</code>.
            </p>

            {sweepParams.map((p, i) => (
              <div key={i} className="flex gap-3 items-end">
                <div className="flex-1">
                  <label className="block text-sm text-content-muted mb-1">Parameter Path</label>
                  <input
                    type="text"
                    value={p.path}
                    onChange={e => {
                      const next = [...sweepParams]
                      next[i] = { ...next[i], path: e.target.value }
                      setSweepParams(next)
                    }}
                    placeholder="variables.rsi_threshold"
                    className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content text-sm font-mono"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-sm text-content-muted mb-1">Values (comma-separated)</label>
                  <input
                    type="text"
                    value={p.values}
                    onChange={e => {
                      const next = [...sweepParams]
                      next[i] = { ...next[i], values: e.target.value }
                      setSweepParams(next)
                    }}
                    placeholder="20, 25, 30, 35"
                    className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content text-sm font-mono"
                  />
                </div>
                <button
                  onClick={() => setSweepParams(sweepParams.filter((_, j) => j !== i))}
                  className="p-2 text-red-400 hover:bg-surface-raised rounded"
                  title="Remove"
                >
                  <Minus size={16} />
                </button>
              </div>
            ))}

            <div className="flex gap-3 items-center">
              <button
                onClick={() => setSweepParams([...sweepParams, { path: '', values: '' }])}
                className="flex items-center gap-1 px-3 py-1.5 bg-surface-raised hover:bg-surface-raised rounded-lg text-sm text-content-muted"
              >
                <Plus size={14} /> Add Parameter
              </button>
              <div>
                <select
                  value={sweepRankBy}
                  onChange={e => setSweepRankBy(e.target.value)}
                  className="bg-surface-inset border border-line rounded-lg px-3 py-1.5 text-content text-sm"
                >
                  <option value="sharpe_ratio">Rank by Sharpe</option>
                  <option value="total_pnl">Rank by P&L</option>
                  <option value="profit_factor">Rank by Profit Factor</option>
                  <option value="win_rate">Rank by Win Rate</option>
                </select>
              </div>
              <button
                onClick={handleSweep}
                disabled={!playbookId || sweepRunning}
                className="flex items-center gap-2 px-5 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
              >
                {sweepRunning ? <Loader2 size={16} className="animate-spin" /> : <GitBranch size={16} />}
                {sweepRunning ? 'Running Sweep...' : 'Run Sweep'}
              </button>
            </div>

            {sweepError && <p className="text-sm text-red-400">{sweepError}</p>}

            {/* Sweep Results */}
            {sweepResult && (
              <div className="space-y-3">
                <div className="flex items-center gap-4 text-sm text-content-muted">
                  <span>{sweepResult.completed}/{sweepResult.total_combinations} runs</span>
                  {sweepResult.failed > 0 && <span className="text-red-400">{sweepResult.failed} failed</span>}
                  <span>{(sweepResult.duration_ms / 1000).toFixed(1)}s</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-surface-raised/50 text-content-muted">
                        <th className="px-3 py-2 text-left">#</th>
                        <th className="px-3 py-2 text-left">Parameters</th>
                        <th className="px-3 py-2 text-right">Trades</th>
                        <th className="px-3 py-2 text-right">Win Rate</th>
                        <th className="px-3 py-2 text-right">P&L</th>
                        <th className="px-3 py-2 text-right">Sharpe</th>
                        <th className="px-3 py-2 text-right">Profit Factor</th>
                        <th className="px-3 py-2 text-right">Max DD%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sweepResult.runs.slice(0, 20).map((r: any) => (
                        <tr key={r.rank} className={`border-t border-line/30 ${r.rank <= 3 ? 'bg-emerald-500/5' : ''}`}>
                          <td className="px-3 py-2 text-content-muted">{r.rank}</td>
                          <td className="px-3 py-2 text-content-secondary font-mono text-xs">
                            {Object.entries(r.params).map(([k, v]) => `${k.split('.').pop()}=${v}`).join(', ')}
                          </td>
                          <td className="px-3 py-2 text-right text-content-secondary">{r.metrics.total_trades}</td>
                          <td className="px-3 py-2 text-right text-content-secondary">{r.metrics.win_rate}%</td>
                          <td className={`px-3 py-2 text-right font-bold ${r.metrics.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            ${r.metrics.total_pnl.toFixed(2)}
                          </td>
                          <td className="px-3 py-2 text-right text-content-secondary">{r.metrics.sharpe_ratio.toFixed(2)}</td>
                          <td className="px-3 py-2 text-right text-content-secondary">{r.metrics.profit_factor.toFixed(2)}</td>
                          <td className="px-3 py-2 text-right text-red-400">{r.metrics.max_drawdown_pct.toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Import Historical Data */}
      <div className="bg-surface-card rounded-xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Upload size={18} className="text-brand-400" />
          <h2 className="text-lg font-semibold text-content">Import Historical Data</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="md:col-span-2 lg:col-span-3">
            <label className="block text-sm text-content-muted mb-1">File Path (local)</label>
            <input
              type="text"
              value={importPath}
              onChange={e => setImportPath(e.target.value)}
              placeholder="D:\data\XAUUSD_ticks_2024.csv"
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content font-mono text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Symbol</label>
            <select
              value={importSymbol}
              onChange={e => setImportSymbol(e.target.value)}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
            >
              {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Timeframe</label>
            <select
              value={importTf}
              onChange={e => setImportTf(e.target.value)}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
            >
              {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Format</label>
            <select
              value={importFormat}
              onChange={e => setImportFormat(e.target.value)}
              className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
            >
              {FORMATS.map(f => (
                <option key={f} value={f}>{f === 'auto' ? 'Auto-detect' : f.toUpperCase()}</option>
              ))}
            </select>
          </div>
          {(importFormat === 'tick_csv' || importFormat === 'auto') && (
            <div>
              <label className="block text-sm text-content-muted mb-1">Price Mode (tick only)</label>
              <select
                value={importPriceMode}
                onChange={e => setImportPriceMode(e.target.value)}
                className="w-full bg-surface-inset border border-line rounded-lg px-3 py-2 text-content"
              >
                {PRICE_MODES.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          )}
        </div>

        <div className="flex gap-3 mt-5">
          <button
            onClick={handleStartImport}
            disabled={!importPath.trim() || importing}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
          >
            <Upload size={16} />
            {importing ? 'Importing...' : 'Start Import'}
          </button>
          {activeJob && (activeJob.status === 'importing' || activeJob.status === 'pending') && (
            <button
              onClick={() => cancelJob(activeJob.id)}
              className="flex items-center gap-2 px-5 py-2.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-sm font-medium transition-colors"
            >
              <X size={16} /> Cancel
            </button>
          )}
          {activeJob && !['importing', 'pending'].includes(activeJob.status) && (
            <button
              onClick={clearJob}
              className="flex items-center gap-2 px-4 py-2.5 bg-surface-raised hover:bg-surface-raised rounded-lg text-sm text-content-muted transition-colors"
            >
              Dismiss
            </button>
          )}
        </div>

        {/* Progress */}
        {activeJob && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-content-muted">
                {activeJob.status === 'importing' ? 'Importing...' :
                 activeJob.status === 'complete' ? 'Complete' :
                 activeJob.status === 'cancelled' ? 'Cancelled' :
                 activeJob.status === 'error' ? 'Error' : activeJob.status}
              </span>
              <span className="text-content-secondary">
                {activeJob.bars_imported.toLocaleString()} bars | {formatBytes(activeJob.bytes_processed)} / {formatBytes(activeJob.file_size)} ({progress}%)
              </span>
            </div>
            <div className="w-full bg-surface-inset rounded-full h-2.5 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  activeJob.status === 'complete' ? 'bg-emerald-500' :
                  activeJob.status === 'error' ? 'bg-red-500' :
                  activeJob.status === 'cancelled' ? 'bg-yellow-500' :
                  'bg-brand-500'
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>
            {activeJob.error && (
              <p className="text-sm text-red-400">{activeJob.error}</p>
            )}
          </div>
        )}

        {importError && !activeJob?.error && (
          <p className="mt-2 text-sm text-red-400">{importError}</p>
        )}
      </div>

      {/* Available Data */}
      <div className="bg-surface-card rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-line/30 flex items-center gap-2">
          <Database size={18} className="text-brand-400" />
          <h2 className="text-lg font-semibold text-content">Available Data</h2>
        </div>
        {summary.length === 0 ? (
          <div className="p-8 text-center text-content-faint">
            No cached bar data. Import data above or fetch from MT5.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-raised/50 text-content-muted">
                <th className="px-4 py-3 text-left">Symbol</th>
                <th className="px-4 py-3 text-left">Timeframe</th>
                <th className="px-4 py-3 text-right">Bars</th>
                <th className="px-4 py-3 text-left">First Date</th>
                <th className="px-4 py-3 text-left">Last Date</th>
                <th className="px-4 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((row, idx) => (
                <tr key={idx} className="border-t border-line/30 hover:bg-surface-raised/30">
                  <td className="px-4 py-3 text-content font-medium">{row.symbol}</td>
                  <td className="px-4 py-3 text-content-secondary">{row.timeframe}</td>
                  <td className="px-4 py-3 text-right text-content-secondary">{row.bar_count.toLocaleString()}</td>
                  <td className="px-4 py-3 text-content-secondary text-xs font-mono">{row.first_date}</td>
                  <td className="px-4 py-3 text-content-secondary text-xs font-mono">{row.last_date}</td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => deleteData(row.symbol, row.timeframe)}
                      className="p-1.5 hover:bg-surface-raised rounded transition-colors text-red-400"
                      title="Delete data"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Recent Runs */}
      <div className="bg-surface-card rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-line/30">
          <h2 className="text-lg font-semibold text-content">Recent Runs</h2>
        </div>
        {loading && !runs.length ? (
          <div className="p-8 text-center text-content-faint">Loading...</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-content-faint">
            No backtest runs yet. Configure and run one above.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-raised/50 text-content-muted">
                <th className="px-4 py-3 text-center w-10"></th>
                <th className="px-4 py-3 text-left">Playbook</th>
                <th className="px-4 py-3 text-left">Symbol</th>
                <th className="px-4 py-3 text-left">TF</th>
                <th className="px-4 py-3 text-right">Bars</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Trades</th>
                <th className="px-4 py-3 text-right">Win Rate</th>
                <th className="px-4 py-3 text-right">P&L</th>
                <th className="px-4 py-3 text-right">Sharpe</th>
                <th className="px-4 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => {
                const m = run.result?.metrics
                const pbName = playbooks.find(p => p.id === run.playbook_id)?.name || `Playbook #${run.playbook_id}`
                return (
                  <tr key={run.id} className="border-t border-line/30 hover:bg-surface-raised/30">
                    <td className="px-4 py-3 text-center">
                      {run.status === 'complete' && (
                        <input
                          type="checkbox"
                          checked={compareIds.includes(run.id)}
                          onChange={() => toggleCompare(run.id)}
                          className="rounded"
                        />
                      )}
                    </td>
                    <td className="px-4 py-3 text-content-secondary" title={pbName}>{pbName}</td>
                    <td className="px-4 py-3 text-content font-medium">{run.symbol}</td>
                    <td className="px-4 py-3 text-content-secondary">{run.timeframe}</td>
                    <td className="px-4 py-3 text-right text-content-secondary">{run.bar_count}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        run.status === 'complete' ? 'bg-emerald-500/20 text-emerald-400' :
                        run.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                        run.status === 'running' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-content-muted/10 text-content-muted'
                      }`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-content-secondary">{m?.total_trades ?? '-'}</td>
                    <td className="px-4 py-3 text-right text-content-secondary">
                      {m?.win_rate != null ? `${m.win_rate}%` : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-bold ${
                      (m?.total_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {m?.total_pnl != null ? `$${m.total_pnl.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-content-secondary">
                      {m?.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : '-'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        {run.status === 'complete' && (
                          <button
                            onClick={() => navigate(`/backtest/${run.id}`)}
                            className="p-1.5 hover:bg-surface-raised rounded transition-colors text-brand-400"
                            title="View result"
                          >
                            <Eye size={15} />
                          </button>
                        )}
                        <button
                          onClick={() => deleteRun(run.id)}
                          className="p-1.5 hover:bg-surface-raised rounded transition-colors text-red-400"
                          title="Delete"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {compareIds.length >= 2 && (
          <div className="px-5 py-3 border-t border-line/30 flex items-center gap-3">
            <span className="text-sm text-content-muted">{compareIds.length} runs selected</span>
            <button
              onClick={handleCompare}
              disabled={comparing}
              className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
            >
              {comparing ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
              Compare
            </button>
            <button onClick={() => { setCompareIds([]); setCompareResult(null) }} className="text-sm text-content-muted hover:text-content">
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Comparison Results */}
      {compareResult && (
        <div className="bg-surface-card rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-line/30">
            <h2 className="text-lg font-semibold text-content">Comparison (baseline: Run #{compareResult.baseline_id})</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-raised/50 text-content-muted">
                  <th className="px-4 py-3 text-left">Run</th>
                  <th className="px-4 py-3 text-left">Symbol / TF</th>
                  <th className="px-4 py-3 text-right">Trades</th>
                  <th className="px-4 py-3 text-right">P&L</th>
                  <th className="px-4 py-3 text-right">Win Rate</th>
                  <th className="px-4 py-3 text-right">Sharpe</th>
                  <th className="px-4 py-3 text-right">Profit Factor</th>
                  <th className="px-4 py-3 text-right">Max DD%</th>
                  <th className="px-4 py-3 text-right">Delta P&L</th>
                  <th className="px-4 py-3 text-right">Delta Sharpe</th>
                </tr>
              </thead>
              <tbody>
                {compareResult.runs.map((r: any, i: number) => (
                  <tr key={r.id} className={`border-t border-line/30 ${i === 0 ? 'bg-brand-500/5' : ''}`}>
                    <td className="px-4 py-3 text-content font-medium">
                      #{r.id} {i === 0 && <span className="text-xs text-brand-400">(baseline)</span>}
                    </td>
                    <td className="px-4 py-3 text-content-secondary">{r.symbol} {r.timeframe}</td>
                    <td className="px-4 py-3 text-right text-content-secondary">{r.trade_count}</td>
                    <td className={`px-4 py-3 text-right font-bold ${r.metrics.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ${r.metrics.total_pnl?.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-content-secondary">{r.metrics.win_rate}%</td>
                    <td className="px-4 py-3 text-right text-content-secondary">{r.metrics.sharpe_ratio?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-content-secondary">{r.metrics.profit_factor?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-red-400">{r.metrics.max_drawdown_pct?.toFixed(1)}%</td>
                    <td className={`px-4 py-3 text-right font-medium ${
                      !r.delta ? 'text-content-muted' : r.delta.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {r.delta ? `${r.delta.total_pnl >= 0 ? '+' : ''}$${r.delta.total_pnl}` : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${
                      !r.delta ? 'text-content-muted' : r.delta.sharpe_ratio >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {r.delta ? `${r.delta.sharpe_ratio >= 0 ? '+' : ''}${r.delta.sharpe_ratio}` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
