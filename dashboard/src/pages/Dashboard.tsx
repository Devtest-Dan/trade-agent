import { useEffect, useState } from 'react'
import { Activity, TrendingUp, Zap, Wallet, Workflow, FlaskConical, Brain } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useMarketStore } from '../store/market'
import { useStrategiesStore } from '../store/strategies'
import { usePlaybooksStore } from '../store/playbooks'

export default function Dashboard() {
  const { account, fetchAccount } = useMarketStore()
  const { strategies, fetch: fetchStrategies } = useStrategiesStore()
  const { playbooks, fetch: fetchPlaybooks } = usePlaybooksStore()
  const [recentSignals, setRecentSignals] = useState<any[]>([])
  const [recentBacktests, setRecentBacktests] = useState<any[]>([])
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    fetchAccount()
    fetchStrategies()
    fetchPlaybooks()
    api.listSignals({ limit: 5 }).then(setRecentSignals).catch(() => {})
    api.listBacktests({ limit: 3 }).then(setRecentBacktests).catch(() => {})
    api.health().then(setHealth).catch(() => {})

    const interval = setInterval(() => {
      fetchAccount()
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const activeStrategies = strategies.filter(s => s.enabled)
  const activePlaybooks = playbooks.filter(p => p.enabled)

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
          sub={`${strategies.length} total + ${activePlaybooks.length}/${playbooks.length} playbooks`}
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

      {/* Strategies */}
      <div className="bg-surface-card rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Brain size={18} className="text-brand-400" />
            Strategies
          </h2>
          <Link to="/strategies" className="text-sm text-brand-400 hover:text-brand-300 transition-colors">
            View all
          </Link>
        </div>
        {strategies.length === 0 ? (
          <p className="text-content-faint">No strategies yet. Create one in the <Link to="/strategies" className="text-brand-400 hover:underline">Strategies</Link> page.</p>
        ) : (
          <div className="space-y-2">
            {strategies.map(s => (
              <Link key={s.id} to="/strategies" className="flex items-center justify-between p-3 bg-surface-raised/50 rounded-lg hover:bg-surface-raised transition-colors">
                <div>
                  <span className="font-medium text-content">{s.name}</span>
                  <span className="ml-3 text-sm text-content-faint">{s.symbols?.join(', ')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded ${
                    s.enabled
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-content-muted/10 text-content-muted'
                  }`}>
                    {s.enabled ? 'Active' : 'Disabled'}
                  </span>
                  <span className={`text-xs px-2 py-1 rounded ${
                    s.autonomy === 'full_auto' ? 'bg-emerald-500/20 text-emerald-400' :
                    s.autonomy === 'semi_auto' ? 'bg-yellow-500/20 text-yellow-400' :
                    'bg-blue-500/20 text-blue-400'
                  }`}>
                    {s.autonomy.replace('_', ' ')}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* All playbooks — show all with status badge */}
      <div className="bg-surface-card rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Workflow size={18} className="text-brand-400" />
            Playbooks
          </h2>
          <Link to="/playbooks" className="text-sm text-brand-400 hover:text-brand-300 transition-colors">
            View all
          </Link>
        </div>
        {playbooks.length === 0 ? (
          <p className="text-content-faint">No playbooks yet. Build one in the <Link to="/playbooks" className="text-brand-400 hover:underline">Playbooks</Link> page.</p>
        ) : (
          <div className="space-y-2">
            {playbooks.map(p => (
              <Link key={p.id} to={`/playbooks/${p.id}`} className="flex items-center justify-between p-3 bg-surface-raised/50 rounded-lg hover:bg-surface-raised transition-colors">
                <div>
                  <span className="font-medium text-content">{p.name}</span>
                  <span className="ml-3 text-sm text-content-faint">
                    {p.symbols?.join(', ')} &middot; {p.phases?.length || 0} phases
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded ${
                    p.enabled
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-content-muted/10 text-content-muted'
                  }`}>
                    {p.enabled ? 'Active' : 'Disabled'}
                  </span>
                  <span className={`text-xs px-2 py-1 rounded ${
                    p.autonomy === 'full_auto' ? 'bg-emerald-500/20 text-emerald-400' :
                    p.autonomy === 'semi_auto' ? 'bg-yellow-500/20 text-yellow-400' :
                    'bg-blue-500/20 text-blue-400'
                  }`}>
                    {p.autonomy?.replace('_', ' ') || 'signal only'}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Recent backtests */}
      <div className="bg-surface-card rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FlaskConical size={18} className="text-brand-400" />
            Recent Backtests
          </h2>
          <Link to="/backtest" className="text-sm text-brand-400 hover:text-brand-300 transition-colors">
            Run backtest
          </Link>
        </div>
        {recentBacktests.length === 0 ? (
          <p className="text-content-faint">No backtests yet. Run one in the <Link to="/backtest" className="text-brand-400 hover:underline">Backtest</Link> page.</p>
        ) : (
          <div className="space-y-2">
            {recentBacktests.map(bt => {
              const m = bt.result?.metrics
              const pbName = playbooks.find((p: any) => p.id === bt.playbook_id)?.name || `Playbook #${bt.playbook_id}`
              return (
                <Link key={bt.id} to={`/backtest/${bt.id}`} className="flex items-center justify-between p-3 bg-surface-raised/50 rounded-lg hover:bg-surface-raised transition-colors">
                  <div>
                    <span className="font-medium text-content">{pbName}</span>
                    <span className="ml-3 text-sm text-content-faint">
                      {bt.symbol} {bt.timeframe} &middot; {bt.bar_count} bars
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    {m && (
                      <>
                        <span className="text-sm text-content-muted">{m.total_trades} trades</span>
                        <span className="text-sm text-content-muted">{m.win_rate}% WR</span>
                        <span className={`text-sm font-bold ${(m.total_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${m.total_pnl?.toFixed(2)}
                        </span>
                      </>
                    )}
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      bt.status === 'complete' ? 'bg-emerald-500/20 text-emerald-400' :
                      bt.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      {bt.status}
                    </span>
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </div>

      {/* Recent signals */}
      <div className="bg-surface-card rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Signals</h2>
        {recentSignals.length === 0 ? (
          <p className="text-content-faint">No signals yet.</p>
        ) : (
          <div className="space-y-2">
            {recentSignals.map(s => (
              <div key={s.id} className="flex items-center justify-between p-3 bg-surface-raised/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <span className={`font-bold ${
                    s.direction.includes('LONG') ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {s.direction}
                  </span>
                  <span className="text-content-secondary">{s.symbol}</span>
                  <span className="text-content-faint text-sm">@ {s.price_at_signal?.toFixed(2)}</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${
                  s.status === 'executed' ? 'bg-emerald-500/20 text-emerald-400' :
                  s.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-content-muted/10 text-content-muted'
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
    <div className="bg-surface-card rounded-xl p-5">
      <div className="flex items-center gap-2 text-content-faint mb-2">
        {icon}
        <span className="text-sm">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-sm text-content-faint mt-1">{sub}</div>
    </div>
  )
}
