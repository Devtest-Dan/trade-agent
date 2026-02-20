import { useEffect, useState } from 'react'
import {
  LineChart, Line, PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api } from '../api/client'

const PIE_COLORS = ['#10b981', '#ef4444', '#f59e0b', '#6366f1', '#8b5cf6', '#ec4899']

export default function Analytics() {
  const [analytics, setAnalytics] = useState<any>(null)
  const [conditions, setConditions] = useState<any[]>([])
  const [trades, setTrades] = useState<any[]>([])
  const [playbooks, setPlaybooks] = useState<any[]>([])
  const [selectedPlaybook, setSelectedPlaybook] = useState<number | undefined>()
  const [loading, setLoading] = useState(true)

  const fetchData = async (playbookId?: number) => {
    setLoading(true)
    try {
      const params = playbookId ? { playbook_id: playbookId } : undefined
      const [analyticsData, condData, tradeData, pbData] = await Promise.all([
        api.getJournalAnalytics(params),
        api.getConditionAnalytics(playbookId),
        api.listJournalEntries({ ...params, limit: 500 }),
        api.listPlaybooks(),
      ])
      setAnalytics(analyticsData)
      setConditions(condData)
      setTrades(tradeData)
      setPlaybooks(pbData)
    } catch {
      // fallback
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchData(selectedPlaybook)
  }, [selectedPlaybook])

  if (loading) {
    return <div className="text-content-faint text-center py-8">Loading analytics...</div>
  }

  // Cumulative PnL curve from trade history
  let cumPnl = 0
  const pnlCurve = trades
    .slice()
    .reverse()
    .map((t: any, i: number) => {
      cumPnl += t.pnl || 0
      return { trade: i + 1, pnl: Math.round(cumPnl * 100) / 100 }
    })

  // Exit reason pie
  const exitReasons = analytics?.exit_reasons || {}
  const pieData = Object.entries(exitReasons).map(([name, value]) => ({ name, value }))

  // Per-playbook breakdown
  const pbMap: Record<number, { name: string; trades: number; wins: number; pnl: number; grossProfit: number; grossLoss: number }> = {}
  trades.forEach((t: any) => {
    const pbId = t.playbook_db_id || 0
    if (!pbMap[pbId]) {
      const pb = playbooks.find((p: any) => p.id === pbId)
      pbMap[pbId] = { name: pb?.name || `Strategy #${pbId}`, trades: 0, wins: 0, pnl: 0, grossProfit: 0, grossLoss: 0 }
    }
    pbMap[pbId].trades++
    if (t.outcome === 'win') pbMap[pbId].wins++
    pbMap[pbId].pnl += t.pnl || 0
    if ((t.pnl || 0) > 0) pbMap[pbId].grossProfit += t.pnl
    else pbMap[pbId].grossLoss += Math.abs(t.pnl || 0)
  })
  const pbStats = Object.values(pbMap)

  // Condition win rates for bar chart
  const condBarData = conditions.slice(0, 10).map((c: any) => ({
    name: c.condition.length > 20 ? c.condition.slice(0, 20) + '...' : c.condition,
    winRate: c.win_rate,
    total: c.total,
  }))

  const totalPnl = analytics?.total_pnl ?? 0
  const profitFactor = analytics?.total_pnl && analytics?.losses
    ? (pbStats.reduce((s, p) => s + p.grossProfit, 0) / (pbStats.reduce((s, p) => s + p.grossLoss, 0) || 1)).toFixed(2)
    : '0.00'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <select
          value={selectedPlaybook ?? ''}
          onChange={e => setSelectedPlaybook(e.target.value ? Number(e.target.value) : undefined)}
          className="bg-surface-inset border border-line rounded-lg px-3 py-2 text-sm text-content"
        >
          <option value="">All Playbooks</option>
          {playbooks.map((p: any) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface-card rounded-xl p-5">
          <div className="text-sm text-content-faint">Total P&L</div>
          <div className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            ${totalPnl.toFixed(2)}
          </div>
        </div>
        <div className="bg-surface-card rounded-xl p-5">
          <div className="text-sm text-content-faint">Win Rate</div>
          <div className="text-2xl font-bold text-brand-400">{analytics?.win_rate ?? 0}%</div>
        </div>
        <div className="bg-surface-card rounded-xl p-5">
          <div className="text-sm text-content-faint">Profit Factor</div>
          <div className="text-2xl font-bold text-content">{profitFactor}</div>
        </div>
        <div className="bg-surface-card rounded-xl p-5">
          <div className="text-sm text-content-faint">Avg R:R</div>
          <div className="text-2xl font-bold text-content">{analytics?.avg_rr?.toFixed(2) ?? '0.00'}</div>
        </div>
      </div>

      {/* Cumulative PnL Curve */}
      {pnlCurve.length > 0 && (
        <div className="bg-surface-card rounded-xl p-5">
          <h2 className="text-lg font-semibold text-content mb-4">Cumulative P&L</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={pnlCurve}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="trade" stroke="var(--chart-text)" tick={{ fontSize: 11 }} label={{ value: 'Trade #', position: 'insideBottom', offset: -5, fill: 'var(--chart-text)' }} />
              <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--chart-text)' }}
                formatter={(val: number) => [`$${val.toFixed(2)}`, 'P&L']}
              />
              <Line type="monotone" dataKey="pnl" stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Exit Reason Pie */}
        {pieData.length > 0 && (
          <div className="bg-surface-card rounded-xl p-5">
            <h2 className="text-lg font-semibold text-content mb-4">Exit Reason Breakdown</h2>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>
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

        {/* Condition Win Rates */}
        {condBarData.length > 0 && (
          <div className="bg-surface-card rounded-xl p-5">
            <h2 className="text-lg font-semibold text-content mb-4">Condition Win Rates</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={condBarData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis type="number" domain={[0, 100]} stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={140} stroke="var(--chart-text)" tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 8 }}
                  formatter={(val: number, name: string) => [`${val}%`, name === 'winRate' ? 'Win Rate' : name]}
                />
                <Bar dataKey="winRate" fill="#10b981" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Per-Playbook Breakdown */}
      {pbStats.length > 0 && (
        <div className="bg-surface-card rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-line/30">
            <h2 className="text-lg font-semibold text-content">Per-Playbook Breakdown</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-raised/50 text-content-muted">
                <th className="px-4 py-3 text-left">Playbook</th>
                <th className="px-4 py-3 text-right">Trades</th>
                <th className="px-4 py-3 text-right">Wins</th>
                <th className="px-4 py-3 text-right">Win Rate</th>
                <th className="px-4 py-3 text-right">P&L</th>
                <th className="px-4 py-3 text-right">Profit Factor</th>
              </tr>
            </thead>
            <tbody>
              {pbStats.map((s, i) => (
                <tr key={i} className="border-t border-line/30">
                  <td className="px-4 py-3 font-medium text-content">{s.name}</td>
                  <td className="px-4 py-3 text-right text-content-secondary">{s.trades}</td>
                  <td className="px-4 py-3 text-right text-emerald-400">{s.wins}</td>
                  <td className="px-4 py-3 text-right text-content-secondary">
                    {s.trades > 0 ? ((s.wins / s.trades) * 100).toFixed(1) : '0.0'}%
                  </td>
                  <td className={`px-4 py-3 text-right font-bold ${s.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    ${s.pnl.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-right text-content-secondary">
                    {s.grossLoss > 0 ? (s.grossProfit / s.grossLoss).toFixed(2) : '0.00'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!analytics?.total_trades && (
        <p className="text-content-faint text-center py-8">
          No journal data yet. Analytics will populate as trades are journaled.
        </p>
      )}
    </div>
  )
}
