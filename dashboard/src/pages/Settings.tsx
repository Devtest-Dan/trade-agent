import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuthStore } from '../store/auth'
import { Save, LogOut } from 'lucide-react'

export default function Settings() {
  const [settings, setSettings] = useState<any>(null)
  const [maxTotalLots, setMaxTotalLots] = useState('')
  const [maxDrawdown, setMaxDrawdown] = useState('')
  const [dailyLossLimit, setDailyLossLimit] = useState('')
  const [saving, setSaving] = useState(false)
  const logout = useAuthStore((s) => s.logout)

  useEffect(() => {
    api.getSettings().then((s) => {
      setSettings(s)
      setMaxTotalLots(String(s.max_total_lots || ''))
      setMaxDrawdown(String(s.max_account_drawdown_pct || ''))
      setDailyLossLimit(String(s.daily_loss_limit || ''))
    }).catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.updateSettings({
        max_total_lots: maxTotalLots ? Number(maxTotalLots) : undefined,
        max_account_drawdown_pct: maxDrawdown ? Number(maxDrawdown) : undefined,
        daily_loss_limit: dailyLossLimit ? Number(dailyLossLimit) : undefined,
      })
      alert('Settings saved')
    } catch (e: any) {
      alert('Error: ' + e.message)
    }
    setSaving(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Connection status */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Connection Status</h2>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${settings?.mt5_connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
          <span className="text-gray-300">
            MT5 {settings?.mt5_connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {settings?.kill_switch_active && (
          <div className="mt-3 flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-red-400 animate-pulse" />
            <span className="text-red-400 font-bold">KILL SWITCH ACTIVE</span>
            <button
              onClick={() => api.deactivateKillSwitch().then(() => window.location.reload())}
              className="ml-4 px-3 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700"
            >
              Deactivate
            </button>
          </div>
        )}
      </div>

      {/* Global risk settings */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Global Risk Limits</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Max Total Lots</label>
            <input
              type="number"
              step="0.01"
              value={maxTotalLots}
              onChange={(e) => setMaxTotalLots(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Max Account Drawdown %</label>
            <input
              type="number"
              step="0.1"
              value={maxDrawdown}
              onChange={(e) => setMaxDrawdown(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Daily Loss Limit ($)</label>
            <input
              type="number"
              step="1"
              value={dailyLossLimit}
              onChange={(e) => setDailyLossLimit(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 focus:outline-none focus:border-brand-500"
            />
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 flex items-center gap-2 px-6 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50"
        >
          <Save size={16} /> {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      {/* Logout */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <button
          onClick={logout}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700"
        >
          <LogOut size={16} /> Logout
        </button>
      </div>
    </div>
  )
}
