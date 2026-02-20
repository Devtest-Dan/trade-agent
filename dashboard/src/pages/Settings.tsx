import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuthStore } from '../store/auth'
import { Save, LogOut, Brain, Key, CheckCircle, AlertCircle, Terminal, Loader2 } from 'lucide-react'

export default function Settings() {
  const [settings, setSettings] = useState<any>(null)
  const [maxTotalLots, setMaxTotalLots] = useState('')
  const [maxDrawdown, setMaxDrawdown] = useState('')
  const [dailyLossLimit, setDailyLossLimit] = useState('')
  const [saving, setSaving] = useState(false)

  // AI config
  const [apiKey, setApiKey] = useState('')
  const [savingKey, setSavingKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const logout = useAuthStore((s) => s.logout)

  const fetchSettings = () => {
    api.getSettings().then((s) => {
      setSettings(s)
      setMaxTotalLots(String(s.max_total_lots || ''))
      setMaxDrawdown(String(s.max_account_drawdown_pct || ''))
      setDailyLossLimit(String(s.daily_loss_limit || ''))
    }).catch(() => {})
  }

  useEffect(() => {
    fetchSettings()
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

  const handleSaveApiKey = async () => {
    setSavingKey(true)
    setTestResult(null)
    try {
      await api.updateSettings({ anthropic_api_key: apiKey })
      setApiKey('')
      fetchSettings()
      setTestResult({ success: true, message: 'API key saved successfully' })
    } catch (e: any) {
      setTestResult({ success: false, message: 'Failed to save: ' + e.message })
    }
    setSavingKey(false)
  }

  const handleClearKey = async () => {
    setSavingKey(true)
    setTestResult(null)
    try {
      await api.updateSettings({ anthropic_api_key: '' })
      setApiKey('')
      fetchSettings()
      setTestResult({ success: true, message: 'API key cleared — using CLI fallback' })
    } catch (e: any) {
      setTestResult({ success: false, message: 'Failed: ' + e.message })
    }
    setSavingKey(false)
  }

  const handleTestAI = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.testAI()
      if (res.success) {
        setTestResult({
          success: true,
          message: `Connected via ${res.provider === 'api' ? 'Anthropic API' : 'Claude Code CLI'} (${res.model})`,
        })
      } else {
        setTestResult({
          success: false,
          message: res.error || 'Test failed',
        })
      }
    } catch (e: any) {
      setTestResult({ success: false, message: e.message })
    }
    setTesting(false)
  }

  const providerLabel = settings?.ai_provider === 'api' ? 'Anthropic API' :
    settings?.ai_provider === 'cli' ? 'Claude Code CLI (Subscription)' : 'Unavailable'

  const providerColor = settings?.ai_provider === 'api' ? 'text-emerald-400' :
    settings?.ai_provider === 'cli' ? 'text-yellow-400' : 'text-red-400'

  const providerBg = settings?.ai_provider === 'api' ? 'bg-emerald-500/20' :
    settings?.ai_provider === 'cli' ? 'bg-yellow-500/20' : 'bg-red-500/20'

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Connection status */}
      <div className="bg-surface-card rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Connection Status</h2>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${settings?.mt5_connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
          <span className="text-content-secondary">
            MT5 {settings?.mt5_connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {settings?.kill_switch_active && (
          <div className="mt-3 flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-red-400 animate-pulse" />
            <span className="text-red-400 font-bold">KILL SWITCH ACTIVE</span>
            <button
              onClick={() => api.deactivateKillSwitch().then(() => window.location.reload())}
              className="ml-4 px-3 py-1 text-sm bg-surface-raised text-content-secondary rounded hover:bg-surface-raised"
            >
              Deactivate
            </button>
          </div>
        )}
      </div>

      {/* AI Configuration */}
      <div className="bg-surface-card rounded-xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Brain size={20} className="text-brand-400" />
          <h2 className="text-lg font-semibold">AI Configuration</h2>
        </div>

        {/* Current provider status */}
        <div className="flex items-center gap-3 mb-5 p-3 bg-surface-raised/50 rounded-lg">
          {settings?.ai_provider === 'api' ? (
            <CheckCircle size={18} className="text-emerald-400" />
          ) : settings?.ai_provider === 'cli' ? (
            <Terminal size={18} className="text-yellow-400" />
          ) : (
            <AlertCircle size={18} className="text-red-400" />
          )}
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-content-muted">Current Provider:</span>
              <span className={`text-sm font-medium px-2 py-0.5 rounded ${providerBg} ${providerColor}`}>
                {providerLabel}
              </span>
            </div>
            {settings?.api_key_set && (
              <div className="text-xs text-content-faint mt-1">
                Key: {settings.api_key_masked}
              </div>
            )}
            {settings?.ai_provider === 'cli' && (
              <div className="text-xs text-content-faint mt-1">
                Using your Claude subscription via Claude Code CLI. Add an API key for faster responses.
              </div>
            )}
          </div>
        </div>

        {/* API Key input */}
        <div className="space-y-3">
          <div>
            <label className="block text-sm text-content-muted mb-1">
              <Key size={14} className="inline mr-1" />
              Anthropic API Key
            </label>
            <input
              type="password"
              placeholder={settings?.api_key_set ? 'Enter new key to replace...' : 'sk-ant-...'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-full px-3 py-2 bg-surface-inset border border-line rounded-lg text-content focus:outline-none focus:border-brand-500 font-mono text-sm"
            />
            <p className="text-xs text-content-faint mt-1">
              Get your API key from{' '}
              <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer"
                className="text-brand-400 hover:underline">
                console.anthropic.com
              </a>
              {' '}— New accounts get $5 free credit. Without a key, AI features use your Claude subscription via CLI.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSaveApiKey}
              disabled={!apiKey || savingKey}
              className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-40 text-sm font-medium transition-colors"
            >
              <Key size={14} />
              {savingKey ? 'Saving...' : 'Save API Key'}
            </button>

            <button
              onClick={handleTestAI}
              disabled={testing}
              className="flex items-center gap-2 px-4 py-2 bg-surface-raised text-content rounded-lg hover:bg-surface-raised disabled:opacity-40 text-sm font-medium transition-colors"
            >
              {testing ? <Loader2 size={14} className="animate-spin" /> : <Brain size={14} />}
              {testing ? 'Testing...' : 'Test Connection'}
            </button>

            {settings?.api_key_set && (
              <button
                onClick={handleClearKey}
                disabled={savingKey}
                className="flex items-center gap-2 px-4 py-2 bg-surface-raised text-red-400 rounded-lg hover:bg-surface-raised disabled:opacity-40 text-sm font-medium transition-colors"
              >
                Clear Key
              </button>
            )}
          </div>

          {/* Test result */}
          {testResult && (
            <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
              testResult.success ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
            }`}>
              {testResult.success ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {testResult.message}
            </div>
          )}
        </div>
      </div>

      {/* Global risk settings */}
      <div className="bg-surface-card rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Global Risk Limits</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-content-muted mb-1">Max Total Lots</label>
            <input
              type="number"
              step="0.01"
              value={maxTotalLots}
              onChange={(e) => setMaxTotalLots(e.target.value)}
              className="w-full px-3 py-2 bg-surface-inset border border-line rounded-lg text-content focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Max Account Drawdown %</label>
            <input
              type="number"
              step="0.1"
              value={maxDrawdown}
              onChange={(e) => setMaxDrawdown(e.target.value)}
              className="w-full px-3 py-2 bg-surface-inset border border-line rounded-lg text-content focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm text-content-muted mb-1">Daily Loss Limit ($)</label>
            <input
              type="number"
              step="1"
              value={dailyLossLimit}
              onChange={(e) => setDailyLossLimit(e.target.value)}
              className="w-full px-3 py-2 bg-surface-inset border border-line rounded-lg text-content focus:outline-none focus:border-brand-500"
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
      <div className="bg-surface-card rounded-xl p-6">
        <button
          onClick={logout}
          className="flex items-center gap-2 px-4 py-2 bg-surface-raised text-content-secondary rounded-lg hover:bg-surface-raised"
        >
          <LogOut size={16} /> Logout
        </button>
      </div>
    </div>
  )
}
