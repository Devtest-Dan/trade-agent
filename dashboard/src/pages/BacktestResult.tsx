import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import {
  LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { useBacktestsStore } from '../store/backtests'
import { usePlaybooksStore } from '../store/playbooks'

const PIE_COLORS = ['#10b981', '#ef4444', '#f59e0b', '#6366f1', '#8b5cf6', '#ec4899']

export default function BacktestResult() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { currentResult, loading, fetchResult } = useBacktestsStore()
  const { playbooks, fetch: fetchPlaybooks } = usePlaybooksStore()

  useEffect(() => {
    if (id) fetchResult(Number(id))
    fetchPlaybooks()
  }, [id])

  if (loading || !currentResult) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-content-faint">Loading backtest result...</div>
      </div>
    )
  }

  const result = currentResult.result
  if (!result) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate('/backtest')} className="flex items-center gap-2 text-content-muted hover:text-content">
          <ArrowLeft size={18} /> Back to Backtests
        </button>
        <p className="text-content-faint">No result data available. Status: {currentResult.status}</p>
      </div>
    )
  }

  const metrics = result.metrics
  const equity = (result.equity_curve || []).map((val: number, i: number) => ({ bar: i, equity: val }))
  const drawdown = (result.drawdown_curve || []).map((val: number, i: number) => ({ bar: i, dd: val }))
  const trades = result.trades || []

  // Exit reason data for pie chart
  const exitReasons: Record<string, number> = {}
  trades.forEach((t: any) => {
    const reason = t.exit_reason || 'unknown'
    exitReasons[reason] = (exitReasons[reason] || 0) + 1
  })
  const pieData = Object.entries(exitReasons).map(([name, value]) => ({ name, value }))

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/backtest')} className="flex items-center gap-2 text-content-muted hover:text-content transition-colors">
          <ArrowLeft size={18} /> Back
        </button>
        <h1 className="text-2xl font-bold">
          {playbooks.find(p => p.id === currentResult.playbook_id)?.name || `Playbook #${currentResult.playbook_id}`} — {currentResult.symbol} {currentResult.timeframe}
        </h1>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total P&L" value={`$${metrics.total_pnl?.toFixed(2)}`} color={metrics.total_pnl >= 0 ? 'emerald' : 'red'} />
        <MetricCard label="Win Rate" value={`${metrics.win_rate}%`} color="brand" />
        <MetricCard label="Sharpe Ratio" value={metrics.sharpe_ratio?.toFixed(2)} color="gray" />
        <MetricCard label="Sortino Ratio" value={metrics.sortino_ratio?.toFixed(2)} color="gray" />
        <MetricCard label="Max Drawdown" value={`${metrics.max_drawdown_pct?.toFixed(1)}%`} color="red" />
        <MetricCard label="Profit Factor" value={metrics.profit_factor?.toFixed(2)} color={metrics.profit_factor >= 1 ? 'emerald' : 'red'} />
        <MetricCard label="Avg R:R" value={metrics.avg_rr?.toFixed(2)} color="gray" />
        <MetricCard label="Recovery Factor" value={metrics.recovery_factor?.toFixed(2)} color="gray" />
        <MetricCard label="Total Trades" value={metrics.total_trades} color="gray" />
        <MetricCard label="Wins / Losses" value={`${metrics.wins} / ${metrics.losses}`} color="gray" />
        <MetricCard label="Consec. Wins" value={metrics.consecutive_wins} color="emerald" />
        <MetricCard label="Consec. Losses" value={metrics.consecutive_losses} color="red" />
      </div>

      {/* Equity Curve */}
      {equity.length > 0 && (
        <div className="bg-surface-card rounded-xl p-5">
          <h2 className="text-lg font-semibold text-content mb-4">Equity Curve</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={equity}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="bar" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--chart-text)' }}
              />
              <Line type="monotone" dataKey="equity" stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Drawdown Chart */}
      {drawdown.length > 0 && (
        <div className="bg-surface-card rounded-xl p-5">
          <h2 className="text-lg font-semibold text-content mb-4">Drawdown</h2>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={drawdown}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="bar" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--chart-text)' }}
              />
              <Area type="monotone" dataKey="dd" stroke="#ef4444" fill="#ef444420" strokeWidth={1.5} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Exit Reason Pie */}
        {pieData.length > 0 && (
          <div className="bg-surface-card rounded-xl p-5">
            <h2 className="text-lg font-semibold text-content mb-4">Exit Reasons</h2>
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 8 }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Quick Stats */}
        <div className="lg:col-span-2 bg-surface-card rounded-xl p-5">
          <h2 className="text-lg font-semibold text-content mb-4">Performance Summary</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex justify-between"><span className="text-content-muted">Avg Win</span><span className="text-emerald-400">${metrics.avg_win?.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-content-muted">Avg Loss</span><span className="text-red-400">${metrics.avg_loss?.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-content-muted">Largest Win</span><span className="text-emerald-400">${metrics.largest_win?.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-content-muted">Largest Loss</span><span className="text-red-400">${metrics.largest_loss?.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-content-muted">Max Drawdown</span><span className="text-red-400">${metrics.max_drawdown?.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-content-muted">Avg Duration</span><span className="text-content">{metrics.avg_duration_bars?.toFixed(0)} bars</span></div>
          </div>
        </div>
      </div>

      {/* Trade List */}
      {trades.length > 0 && (
        <div className="bg-surface-card rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-line/30">
            <h2 className="text-lg font-semibold text-content">Trades ({trades.length})</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-raised/50 text-content-muted">
                  <th className="px-3 py-2.5 text-left">#</th>
                  <th className="px-3 py-2.5 text-left">Dir</th>
                  <th className="px-3 py-2.5 text-right">Entry</th>
                  <th className="px-3 py-2.5 text-right">Exit</th>
                  <th className="px-3 py-2.5 text-right">SL</th>
                  <th className="px-3 py-2.5 text-right">TP</th>
                  <th className="px-3 py-2.5 text-right">P&L</th>
                  <th className="px-3 py-2.5 text-right">Pips</th>
                  <th className="px-3 py-2.5 text-right">R:R</th>
                  <th className="px-3 py-2.5 text-center">Outcome</th>
                  <th className="px-3 py-2.5 text-left">Exit</th>
                  <th className="px-3 py-2.5 text-right">Bars</th>
                  <th className="px-3 py-2.5 text-left">Phase</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t: any, i: number) => (
                  <tr key={i} className="border-t border-line/30 hover:bg-surface-raised/30">
                    <td className="px-3 py-2 text-content-muted">{i + 1}</td>
                    <td className={`px-3 py-2 font-medium ${t.direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                      {t.direction}
                    </td>
                    <td className="px-3 py-2 text-right text-content-secondary">{t.open_price?.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-content-secondary">{t.close_price?.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-content-faint">{t.sl?.toFixed(2) ?? '-'}</td>
                    <td className="px-3 py-2 text-right text-content-faint">{t.tp?.toFixed(2) ?? '-'}</td>
                    <td className={`px-3 py-2 text-right font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ${t.pnl?.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 text-right text-content-secondary">{t.pnl_pips?.toFixed(1)}</td>
                    <td className="px-3 py-2 text-right text-content-secondary">{t.rr_achieved?.toFixed(2) ?? '-'}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        t.outcome === 'win' ? 'bg-emerald-500/20 text-emerald-400' :
                        t.outcome === 'loss' ? 'bg-red-500/20 text-red-400' :
                        'bg-content-muted/10 text-content-muted'
                      }`}>
                        {t.outcome}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-content-muted">{t.exit_reason}</td>
                    <td className="px-3 py-2 text-right text-content-muted">{t.close_idx - t.open_idx}</td>
                    <td className="px-3 py-2 text-content-faint">{t.phase_at_entry}</td>
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

function MetricCard({ label, value, color }: { label: string; value: any; color: string }) {
  const colorMap: Record<string, string> = {
    emerald: 'text-emerald-400',
    red: 'text-red-400',
    brand: 'text-brand-400',
    gray: 'text-content',
  }
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <div className="text-xs text-content-faint mb-1">{label}</div>
      <div className={`text-xl font-bold ${colorMap[color] || 'text-content'}`}>{value}</div>
    </div>
  )
}
