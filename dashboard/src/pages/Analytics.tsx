import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function Analytics() {
  const [trades, setTrades] = useState<any[]>([])
  const [strategies, setStrategies] = useState<any[]>([])

  useEffect(() => {
    api.listTrades({ limit: 500 }).then(setTrades).catch(() => {})
    api.listStrategies().then(setStrategies).catch(() => {})
  }, [])

  // Compute analytics per strategy
  const strategyStats = strategies.map(s => {
    const st = trades.filter(t => t.strategy_id === s.id)
    const wins = st.filter(t => t.pnl && t.pnl > 0)
    const losses = st.filter(t => t.pnl && t.pnl < 0)
    const totalPnl = st.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const grossProfit = wins.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const grossLoss = Math.abs(losses.reduce((sum, t) => sum + (t.pnl || 0), 0))

    return {
      name: s.name,
      id: s.id,
      trades: st.length,
      wins: wins.length,
      losses: losses.length,
      winRate: st.length > 0 ? ((wins.length / st.length) * 100).toFixed(1) : '0.0',
      totalPnl: totalPnl.toFixed(2),
      profitFactor: grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : '0.00',
    }
  })

  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl || 0), 0)
  const totalTrades = trades.length
  const totalWins = trades.filter(t => t.pnl && t.pnl > 0).length

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analytics</h1>

      {/* Overall stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <div className="text-sm text-gray-500">Total P&L</div>
          <div className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            ${totalPnl.toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <div className="text-sm text-gray-500">Total Trades</div>
          <div className="text-2xl font-bold text-gray-100">{totalTrades}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <div className="text-sm text-gray-500">Win Rate</div>
          <div className="text-2xl font-bold text-brand-400">
            {totalTrades > 0 ? ((totalWins / totalTrades) * 100).toFixed(1) : '0.0'}%
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <div className="text-sm text-gray-500">Strategies</div>
          <div className="text-2xl font-bold text-gray-100">{strategies.length}</div>
        </div>
      </div>

      {/* Per-strategy breakdown */}
      {strategyStats.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-800/50 text-gray-400">
                <th className="px-4 py-3 text-left">Strategy</th>
                <th className="px-4 py-3 text-right">Trades</th>
                <th className="px-4 py-3 text-right">Wins</th>
                <th className="px-4 py-3 text-right">Losses</th>
                <th className="px-4 py-3 text-right">Win Rate</th>
                <th className="px-4 py-3 text-right">P&L</th>
                <th className="px-4 py-3 text-right">Profit Factor</th>
              </tr>
            </thead>
            <tbody>
              {strategyStats.map(s => (
                <tr key={s.id} className="border-t border-gray-800">
                  <td className="px-4 py-3 font-medium text-gray-200">{s.name}</td>
                  <td className="px-4 py-3 text-right text-gray-300">{s.trades}</td>
                  <td className="px-4 py-3 text-right text-emerald-400">{s.wins}</td>
                  <td className="px-4 py-3 text-right text-red-400">{s.losses}</td>
                  <td className="px-4 py-3 text-right text-gray-300">{s.winRate}%</td>
                  <td className={`px-4 py-3 text-right font-bold ${
                    Number(s.totalPnl) >= 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    ${s.totalPnl}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-300">{s.profitFactor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {strategyStats.length === 0 && (
        <p className="text-gray-500 text-center py-8">
          No data yet. Analytics will populate as trades are executed.
        </p>
      )}
    </div>
  )
}
