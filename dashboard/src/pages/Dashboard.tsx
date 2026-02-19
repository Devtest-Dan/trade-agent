import { useEffect, useState } from 'react'
import { Activity, TrendingUp, Zap, Wallet } from 'lucide-react'
import { api } from '../api/client'
import { useMarketStore } from '../store/market'
import { useStrategiesStore } from '../store/strategies'

export default function Dashboard() {
  const { account, fetchAccount } = useMarketStore()
  const { strategies, fetch: fetchStrategies } = useStrategiesStore()
  const [recentSignals, setRecentSignals] = useState<any[]>([])
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    fetchAccount()
    fetchStrategies()
    api.listSignals({ limit: 5 }).then(setRecentSignals).catch(() => {})
    api.health().then(setHealth).catch(() => {})

    const interval = setInterval(() => {
      fetchAccount()
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const activeStrategies = strategies.filter(s => s.enabled)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Wallet size={20} />}
          label="Balance"
          value={account?.balance ? `$${account.balance.toFixed(2)}` : '--'}
          sub={account?.equity ? `Equity: $${account.equity.toFixed(2)}` : 'Not connected'}
          color="text-brand-400"
        />
        <StatCard
          icon={<TrendingUp size={20} />}
          label="Profit"
          value={account?.profit !== undefined ? `$${account.profit.toFixed(2)}` : '--'}
          sub={account?.free_margin ? `Free: $${account.free_margin.toFixed(2)}` : ''}
          color={account?.profit && account.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}
        />
        <StatCard
          icon={<Zap size={20} />}
          label="Active Strategies"
          value={String(activeStrategies.length)}
          sub={`${strategies.length} total`}
          color="text-yellow-400"
        />
        <StatCard
          icon={<Activity size={20} />}
          label="MT5 Status"
          value={health?.mt5_connected ? 'Connected' : 'Offline'}
          sub={health?.kill_switch ? 'KILL SWITCH ON' : 'Normal'}
          color={health?.mt5_connected ? 'text-emerald-400' : 'text-red-400'}
        />
      </div>

      {/* Active strategies */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Active Strategies</h2>
        {activeStrategies.length === 0 ? (
          <p className="text-gray-500">No active strategies. Create one in the Strategies page.</p>
        ) : (
          <div className="space-y-2">
            {activeStrategies.map(s => (
              <div key={s.id} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
                <div>
                  <span className="font-medium text-gray-200">{s.name}</span>
                  <span className="ml-3 text-sm text-gray-500">{s.symbols?.join(', ')}</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${
                  s.autonomy === 'full_auto' ? 'bg-emerald-500/20 text-emerald-400' :
                  s.autonomy === 'semi_auto' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-blue-500/20 text-blue-400'
                }`}>
                  {s.autonomy.replace('_', ' ')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent signals */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Signals</h2>
        {recentSignals.length === 0 ? (
          <p className="text-gray-500">No signals yet.</p>
        ) : (
          <div className="space-y-2">
            {recentSignals.map(s => (
              <div key={s.id} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <span className={`font-bold ${
                    s.direction.includes('LONG') ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {s.direction}
                  </span>
                  <span className="text-gray-300">{s.symbol}</span>
                  <span className="text-gray-500 text-sm">@ {s.price_at_signal?.toFixed(2)}</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${
                  s.status === 'executed' ? 'bg-emerald-500/20 text-emerald-400' :
                  s.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-gray-500/20 text-gray-400'
                }`}>
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ icon, label, value, sub, color }: {
  icon: React.ReactNode
  label: string
  value: string
  sub: string
  color: string
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <div className="flex items-center gap-2 text-gray-500 mb-2">
        {icon}
        <span className="text-sm">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-sm text-gray-500 mt-1">{sub}</div>
    </div>
  )
}
