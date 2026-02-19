import { useEffect } from 'react'
import { Routes, Route, Navigate, NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Brain,
  Zap,
  LineChart,
  BarChart3,
  Settings as SettingsIcon,
  Bot,
} from 'lucide-react'

import { useAuthStore } from './store/auth'
import { useMarketStore } from './store/market'
import { useSignalsStore } from './store/signals'
import { wsClient } from './api/ws'

import KillSwitch from './components/KillSwitch'
import LiveTicker from './components/LiveTicker'

import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import StrategyEditor from './pages/StrategyEditor'
import Signals from './pages/Signals'
import Trades from './pages/Trades'
import Analytics from './pages/Analytics'
import SettingsPage from './pages/Settings'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/strategies', icon: Brain, label: 'Strategies' },
  { to: '/signals', icon: Zap, label: 'Signals' },
  { to: '/trades', icon: LineChart, label: 'Trades' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/settings', icon: SettingsIcon, label: 'Settings' },
]

export default function App() {
  const { isAuthenticated, checkAuth } = useAuthStore()
  const updateTick = useMarketStore((s) => s.updateTick)
  const addSignal = useSignalsStore((s) => s.addSignal)

  useEffect(() => {
    checkAuth()
  }, [])

  // Wire up WebSocket events
  useEffect(() => {
    wsClient.on('tick', (data) => {
      updateTick(data.symbol, data.bid, data.ask, data.timestamp)
    })
    wsClient.on('signal', (data) => {
      addSignal(data)
    })
  }, [])

  if (!isAuthenticated) {
    return <Login />
  }

  return (
    <div className="min-h-screen bg-gray-950 flex">
      {/* Sidebar */}
      <nav className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-6 flex items-center gap-3">
          <Bot size={28} className="text-brand-500" />
          <span className="text-lg font-bold text-gray-100">Trade Agent</span>
        </div>

        <div className="flex-1 px-3 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-600/20 text-brand-400'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="p-4">
          <KillSwitch />
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 flex flex-col">
        {/* Top bar */}
        <header className="h-14 border-b border-gray-800 px-6 flex items-center justify-between bg-gray-900/50">
          <LiveTicker />
          <div className="text-sm text-gray-500">
            AI-Powered MT5 Trading
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 p-6 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/strategies/:id" element={<StrategyEditor />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/trades" element={<Trades />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/login" element={<Navigate to="/" />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
