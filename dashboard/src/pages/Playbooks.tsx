import { useEffect, useState } from 'react'
import { Plus, Loader2 } from 'lucide-react'
import { usePlaybooksStore } from '../store/playbooks'
import PlaybookCard from '../components/PlaybookCard'
import IndicatorPanel from '../components/IndicatorPanel'

export default function Playbooks() {
  const { playbooks, loading, fetch, build, toggle, remove } = usePlaybooksStore()
  const [showCreate, setShowCreate] = useState(false)
  const [description, setDescription] = useState('')
  const [building, setBuilding] = useState(false)
  const [buildResult, setBuildResult] = useState<any>(null)

  useEffect(() => { fetch() }, [])

  const handleBuild = async () => {
    if (!description.trim()) return
    setBuilding(true)
    setBuildResult(null)
    try {
      const result = await build(description)
      setBuildResult(result)
      setDescription('')
    } catch (e: any) {
      alert('Error: ' + e.message)
    }
    setBuilding(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Playbooks</h1>
        <button
          onClick={() => { setShowCreate(!showCreate); setBuildResult(null) }}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus size={18} /> New Playbook
        </button>
      </div>

      {/* Indicator reference */}
      <IndicatorPanel />

      {/* Build playbook panel */}
      {showCreate && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-3">Describe Your Playbook</h2>
          <p className="text-sm text-gray-400 mb-4">
            Describe your trading strategy in natural language. The AI will build a multi-phase execution playbook with entry conditions, position management rules, and exit logic.
          </p>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Example: On H1, wait for price to enter the OTE zone with bullish SMC structure. Switch to M15, enter long when RSI crosses above 40 and price closes above the FVG upper boundary. Set SL below the swing low, TP at 2R. Trail stop at 1.5 ATR after 1R profit."
            className="w-full h-36 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:border-brand-500 resize-none"
          />
          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={handleBuild}
              disabled={building || !description.trim()}
              className="flex items-center gap-2 px-6 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {building && <Loader2 size={16} className="animate-spin" />}
              {building ? 'Building Playbook...' : 'Build Playbook'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 text-gray-400 hover:text-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>

          {/* Build result */}
          {buildResult && (
            <div className="mt-4 bg-gray-800 rounded-lg p-4">
              <h3 className="font-medium text-emerald-400 mb-2">Playbook Built Successfully</h3>
              <p className="text-sm text-gray-300 mb-1">Name: {buildResult.name}</p>
              {buildResult.skills_used?.length > 0 && (
                <p className="text-sm text-gray-500 mb-2">
                  Skills used: {buildResult.skills_used.join(', ')}
                </p>
              )}
              {buildResult.usage && (
                <p className="text-xs text-gray-600 mb-2">
                  Tokens: {buildResult.usage.prompt_tokens} in / {buildResult.usage.completion_tokens} out
                  ({buildResult.usage.duration_ms}ms)
                </p>
              )}
              <details>
                <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-200">
                  View playbook config (JSON)
                </summary>
                <pre className="mt-2 text-xs text-gray-300 overflow-auto max-h-64 bg-gray-900 p-3 rounded">
                  {JSON.stringify(buildResult.config, null, 2)}
                </pre>
              </details>
              <p className="text-sm text-gray-500 mt-2">
                Playbook is created but disabled. Enable it to start receiving signals.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Playbook list */}
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="animate-spin text-gray-500" size={32} />
        </div>
      ) : playbooks.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p>No playbooks yet. Click "New Playbook" to build one with AI.</p>
          <p className="text-sm mt-2 text-gray-600">
            Playbooks are multi-phase state machines — more powerful than flat strategies.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {playbooks.map(p => (
            <PlaybookCard
              key={p.id}
              playbook={p}
              onToggle={toggle}
              onDelete={remove}
            />
          ))}
        </div>
      )}
    </div>
  )
}
