import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, MessageSquare, X } from 'lucide-react'
import { api } from '../api/client'
import StrategyChat from '../components/StrategyChat'

export default function StrategyEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [strategy, setStrategy] = useState<any>(null)
  const [configJson, setConfigJson] = useState('')
  const [saving, setSaving] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)

  useEffect(() => {
    if (id) {
      api.getStrategy(Number(id)).then((s) => {
        setStrategy(s)
        setConfigJson(JSON.stringify(s.config, null, 2))
      })
    }
  }, [id])

  const handleSave = async () => {
    setSaving(true)
    try {
      const config = JSON.parse(configJson)
      await api.updateStrategy(Number(id), { config })
      alert('Strategy updated')
    } catch (e: any) {
      alert('Error: ' + e.message)
    }
    setSaving(false)
  }

  const handleApplyConfig = async (config: any) => {
    const json = JSON.stringify(config, null, 2)
    setConfigJson(json)
    // Auto-save
    setSaving(true)
    try {
      await api.updateStrategy(Number(id), { config })
    } catch (e: any) {
      alert('Failed to save applied config: ' + e.message)
    }
    setSaving(false)
  }

  if (!strategy) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/strategies')}
            className="p-2 text-gray-400 hover:text-gray-200"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold">{strategy.name}</h1>
            <p className="text-sm text-gray-500">{strategy.description}</p>
          </div>
        </div>
        <button
          onClick={() => setChatOpen(!chatOpen)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
            chatOpen
              ? 'bg-gray-700 text-gray-200'
              : 'bg-brand-600/20 text-brand-400 hover:bg-brand-600/30'
          }`}
        >
          {chatOpen ? <X size={16} /> : <MessageSquare size={16} />}
          {chatOpen ? 'Close Chat' : 'Discuss with AI'}
        </button>
      </div>

      {/* 2-column layout: config left, chat right */}
      <div className={`grid gap-6 ${chatOpen ? 'lg:grid-cols-[2fr_1fr]' : 'grid-cols-1'}`}>
        {/* Left column — config */}
        <div className="space-y-6 min-w-0">
          {/* Natural language description */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-2">Original Description</h2>
            <p className="text-gray-300">{strategy.description}</p>
          </div>

          {/* Config editor */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Parsed Config</h2>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50"
              >
                <Save size={16} /> {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
            <textarea
              value={configJson}
              onChange={(e) => setConfigJson(e.target.value)}
              className="w-full h-96 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 font-mono text-sm focus:outline-none focus:border-brand-500 resize-y"
              spellCheck={false}
            />
          </div>
        </div>

        {/* Right column — chat (sticky on desktop) */}
        {chatOpen && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-6rem)] flex flex-col min-h-[400px]">
            <div className="px-4 py-3 border-b border-gray-800">
              <h2 className="text-sm font-semibold text-gray-300">AI Strategy Chat</h2>
            </div>
            <StrategyChat
              strategyId={Number(id)}
              onApplyConfig={handleApplyConfig}
            />
          </div>
        )}
      </div>
    </div>
  )
}
