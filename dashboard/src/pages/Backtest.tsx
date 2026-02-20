import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FlaskConical, Play, Trash2, Download, Eye } from 'lucide-react'
import { useBacktestsStore } from '../store/backtests'
import { usePlaybooksStore } from '../store/playbooks'
import { api } from '../api/client'

const SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'GBPJPY', 'EURJPY']
const TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1']

export default function Backtest() {
  const navigate = useNavigate()
  const { runs, loading, error, fetchRuns, startBacktest, deleteRun } = useBacktestsStore()
  const { playbooks, fetch: fetchPlaybooks } = usePlaybooksStore()

  const [playbookId, setPlaybookId] = useState<number>(0)
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('H4')
  const [barCount, setBarCount] = useState(500)
  const [spreadPips, setSpreadPips] = useState(0.3)
  const [startingBalance, setStartingBalance] = useState(10000)
  const [running, setRunning] = useState(false)
  const [fetchingBars, setFetchingBars] = useState(false)
  const [fetchMsg, setFetchMsg] = useState('')

  useEffect(() => {
    fetchPlaybooks()
    fetchRuns()
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

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <FlaskConical size={24} className="text-brand-400" />
        <h1 className="text-2xl font-bold">Backtest</h1>
      </div>

      {/* Config Form */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Configuration</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Playbook</label>
            <select
              value={playbookId}
              onChange={e => setPlaybookId(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200"
            >
              <option value={0}>Select playbook...</option>
              {playbooks.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Symbol</label>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200"
            >
              {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200"
            >
              {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Bar Count</label>
            <input
              type="number"
              value={barCount}
              onChange={e => setBarCount(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200"
              min={60}
              max={5000}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Spread (pips)</label>
            <input
              type="number"
              value={spreadPips}
              onChange={e => setSpreadPips(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200"
              step={0.1}
              min={0}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Starting Balance ($)</label>
            <input
              type="number"
              value={startingBalance}
              onChange={e => setStartingBalance(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200"
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
            className="flex items-center gap-2 px-5 py-2.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
          >
            <Download size={16} />
            {fetchingBars ? 'Fetching...' : 'Fetch Bars from MT5'}
          </button>
        </div>

        {fetchMsg && <p className="mt-2 text-sm text-gray-400">{fetchMsg}</p>}
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </div>

      {/* Recent Runs */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-gray-200">Recent Runs</h2>
        </div>
        {loading && !runs.length ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No backtest runs yet. Configure and run one above.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-800/50 text-gray-400">
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
                  <tr key={run.id} className="border-t border-gray-800 hover:bg-gray-800/30">
                    <td className="px-4 py-3 text-gray-300" title={pbName}>{pbName}</td>
                    <td className="px-4 py-3 text-gray-200 font-medium">{run.symbol}</td>
                    <td className="px-4 py-3 text-gray-300">{run.timeframe}</td>
                    <td className="px-4 py-3 text-right text-gray-300">{run.bar_count}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        run.status === 'complete' ? 'bg-emerald-500/20 text-emerald-400' :
                        run.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                        run.status === 'running' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">{m?.total_trades ?? '-'}</td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      {m?.win_rate != null ? `${m.win_rate}%` : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-bold ${
                      (m?.total_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {m?.total_pnl != null ? `$${m.total_pnl.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      {m?.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : '-'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        {run.status === 'complete' && (
                          <button
                            onClick={() => navigate(`/backtest/${run.id}`)}
                            className="p-1.5 hover:bg-gray-700 rounded transition-colors text-brand-400"
                            title="View result"
                          >
                            <Eye size={15} />
                          </button>
                        )}
                        <button
                          onClick={() => deleteRun(run.id)}
                          className="p-1.5 hover:bg-gray-700 rounded transition-colors text-red-400"
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
      </div>
    </div>
  )
}
