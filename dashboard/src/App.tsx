import { useEffect, lazy, Suspense } from 'react'
import { Routes, Route, Navigate, NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Brain,
  Workflow,
  Zap,
  LineChart,
  CandlestickChart as CandlestickIcon,
  BarChart3,
  BookOpen,
  FlaskConical,
  Gauge,
  Settings as SettingsIcon,
  Bot,
  Sun,
  Moon,
  Loader2,
} from 'lucide-react'

import { useAuthStore } from './store/auth'
import { useMarketStore } from './store/market'
import { useSignalsStore } from './store/signals'
import { useThemeStore } from './store/theme'
import { wsClient } from './api/ws'

import KillSwitch from './components/KillSwitch'
import LiveTicker from './components/LiveTicker'

// Login stays eager — it's the auth gate
import Login from './pages/Login'

// Lazy-load all page components
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Strategies = lazy(() => import('./pages/Strategies'))
const StrategyEditor = lazy(() => import('./pages/StrategyEditor'))
const Playbooks = lazy(() => import('./pages/Playbooks'))
const PlaybookEditor = lazy(() => import('./pages/PlaybookEditor'))
const Signals = lazy(() => import('./pages/Signals'))
const Trades = lazy(() => import('./pages/Trades'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Journal = lazy(() => import('./pages/Journal'))
const BacktestPage = lazy(() => import('./pages/Backtest'))
const BacktestResultPage = lazy(() => import('./pages/BacktestResult'))
const Indicators = lazy(() => import('./pages/Indicators'))
const ChartPage = lazy(() => import('./pages/Chart'))
const SettingsPage = lazy(() => import('./pages/Settings'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="animate-spin text-content-faint" size={28} />
    </div>
  )
}

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/strategies', icon: Brain, label: 'Strategies' },
  { to: '/playbooks', icon: Workflow, label: 'Playbooks' },
  { to: '/signals', icon: Zap, label: 'Signals' },
  { to: '/trades', icon: LineChart, label: 'Trades' },
  { to: '/chart', icon: CandlestickIcon, label: 'Chart' },
  { to: '/journal', icon: BookOpen, label: 'Journal' },
  { to: '/backtest', icon: FlaskConical, label: 'Backtest' },
  { to: '/indicators', icon: Gauge, label: 'Indicators' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/settings', icon: SettingsIcon, label: 'Settings' },
]

export default function App() {
  const { isAuthenticated, checking, checkAuth } = useAuthStore()
  const updateTick = useMarketStore((s) => s.updateTick)
  const addSignal = useSignalsStore((s) => s.addSignal)
  const { dark, toggle: toggleTheme } = useThemeStore()

  useEffect(() => {
    checkAuth()
  }, [])

  useEffect(() => {
    wsClient.on('tick', (data) => {
      updateTick(data.symbol, data.bid, data.ask, data.timestamp)
    })
    wsClient.on('signal', (data) => {
      addSignal(data)
    })
  }, [])

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-page">
        <div className="text-content-muted">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Login />
  }

  return (
    <div className="min-h-screen bg-surface-page flex">
      {/* Sidebar */}
      <nav className="w-56 bg-surface-nav border-r border-line/40 flex flex-col">
        <div className="p-5 flex items-center gap-3">
          <Bot size={24} className="text-brand-500" />
          <span className="text-base font-semibold text-content">Trade Agent</span>
        </div>

        <div className="flex-1 px-3 space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-600/10 text-brand-500 font-medium'
                    : 'text-content-muted hover:text-content hover:bg-surface-raised/60'
                }`
              }
            >
              <item.icon size={17} />
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="p-3 space-y-2">
          <KillSwitch />
          <button
            onClick={toggleTheme}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-content-muted hover:text-content hover:bg-surface-raised/60 transition-colors"
          >
            {dark ? <Sun size={17} /> : <Moon size={17} />}
            {dark ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-12 border-b border-line/40 px-6 flex items-center justify-between">
          <LiveTicker />
          <div className="text-xs text-content-faint">
            AI-Powered MT5 Trading
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 p-6 overflow-auto">
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/strategies" element={<Strategies />} />
              <Route path="/strategies/:id" element={<StrategyEditor />} />
              <Route path="/playbooks" element={<Playbooks />} />
              <Route path="/playbooks/:id" element={<PlaybookEditor />} />
              <Route path="/signals" element={<Signals />} />
              <Route path="/trades" element={<Trades />} />
              <Route path="/chart" element={<ChartPage />} />
              <Route path="/journal" element={<Journal />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/backtest/:id" element={<BacktestResultPage />} />
              <Route path="/indicators" element={<Indicators />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/login" element={<Navigate to="/" />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  )
}
