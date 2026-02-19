import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { directionColor, formatDate } from '../lib/utils'
import { Loader2 } from 'lucide-react'

export default function Trades() {
  const [trades, setTrades] = useState<any[]>([])
  const [positions, setPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'history' | 'open'>('history')

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [])

  const loadData = async () => {
    try {
      const [t, p] = await Promise.all([
        api.listTrades({ limit: 50 }),
        api.getOpenPositions(),
      ])
      setTrades(t)
      setPositions(p)
    } catch { /* offline */ }
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trades</h1>

      <div className="flex gap-2">
        <button
          onClick={() => setTab('history')}
          className={`px-4 py-2 rounded-lg text-sm font-medium ${
            tab === 'history' ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400'
          }`}
        >
          History ({trades.length})
        </button>
        <button
          onClick={() => setTab('open')}
          className={`px-4 py-2 rounded-lg text-sm font-medium ${
            tab === 'open' ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400'
          }`}
        >
          Open Positions ({positions.length})
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="animate-spin text-gray-500" size={32} />
        </div>
      ) : tab === 'history' ? (
        trades.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No trade history yet.</p>
        ) : (
          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-800/50 text-gray-400">
                  <th className="px-4 py-3 text-left">Symbol</th>
                  <th className="px-4 py-3 text-left">Direction</th>
                  <th className="px-4 py-3 text-right">Lot</th>
                  <th className="px-4 py-3 text-right">Open</th>
                  <th className="px-4 py-3 text-right">Close</th>
                  <th className="px-4 py-3 text-right">P&L</th>
                  <th className="px-4 py-3 text-right">Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.map(t => (
                  <tr key={t.id} className="border-t border-gray-800">
                    <td className="px-4 py-3 font-medium text-gray-200">{t.symbol}</td>
                    <td className={`px-4 py-3 font-bold ${directionColor(t.direction)}`}>{t.direction}</td>
                    <td className="px-4 py-3 text-right text-gray-300">{t.lot}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{t.open_price?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{t.close_price?.toFixed(2) || '--'}</td>
                    <td className={`px-4 py-3 text-right font-bold ${
                      t.pnl > 0 ? 'text-emerald-400' : t.pnl < 0 ? 'text-red-400' : 'text-gray-400'
                    }`}>
                      {t.pnl !== null ? `$${t.pnl.toFixed(2)}` : '--'}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500">{t.open_time ? formatDate(t.open_time) : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        positions.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No open positions.</p>
        ) : (
          <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-800/50 text-gray-400">
                  <th className="px-4 py-3 text-left">Ticket</th>
                  <th className="px-4 py-3 text-left">Symbol</th>
                  <th className="px-4 py-3 text-left">Dir</th>
                  <th className="px-4 py-3 text-right">Lot</th>
                  <th className="px-4 py-3 text-right">Open</th>
                  <th className="px-4 py-3 text-right">Current</th>
                  <th className="px-4 py-3 text-right">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(p => (
                  <tr key={p.ticket} className="border-t border-gray-800">
                    <td className="px-4 py-3 text-gray-400">{p.ticket}</td>
                    <td className="px-4 py-3 font-medium text-gray-200">{p.symbol}</td>
                    <td className={`px-4 py-3 font-bold ${directionColor(p.direction)}`}>{p.direction}</td>
                    <td className="px-4 py-3 text-right text-gray-300">{p.lot}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{p.open_price?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{p.current_price?.toFixed(2)}</td>
                    <td className={`px-4 py-3 text-right font-bold ${
                      p.pnl > 0 ? 'text-emerald-400' : p.pnl < 0 ? 'text-red-400' : 'text-gray-400'
                    }`}>
                      ${p.pnl?.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
