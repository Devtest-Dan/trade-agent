import { useEffect, useState } from 'react'
import { Plus, Loader2 } from 'lucide-react'
import { useStrategiesStore } from '../store/strategies'
import StrategyCard from '../components/StrategyCard'
import IndicatorPanel from '../components/IndicatorPanel'

export default function Strategies() {
  const { strategies, loading, fetch, create, toggle, setAutonomy, remove } = useStrategiesStore()
  const [showCreate, setShowCreate] = useState(false)
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [parseResult, setParseResult] = useState<any>(null)

  useEffect(() => { fetch() }, [])

  const handleCreate = async () => {
    if (!description.trim()) return
    setCreating(true)
    try {
      const result = await create(description)
      setParseResult(result)
      setDescription('')
    } catch (e: any) {
      alert('Error: ' + e.message)
    }
    setCreating(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Strategies</h1>
        <button
          onClick={() => { setShowCreate(!showCreate); setParseResult(null) }}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus size={18} /> New Strategy
        </button>
      </div>

      {/* Indicator reference */}
      <IndicatorPanel />

      {/* Create strategy panel */}
      {showCreate && (
        <div className="bg-surface-card rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-3">Describe Your Strategy</h2>
          <p className="text-sm text-content-muted mb-4">
            Describe your trading strategy in natural language. The AI will parse it into executable conditions.
          </p>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Example: On H4, when RSI(14) is below 30 and EMA(50) is above price, switch to M15 and enter long when Stochastic K crosses above 20."
            className="w-full h-32 px-4 py-3 bg-surface-inset border border-line rounded-lg text-content placeholder-content-muted focus:outline-none focus:border-brand-500 resize-none"
          />
          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={handleCreate}
              disabled={creating || !description.trim()}
              className="flex items-center gap-2 px-6 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {creating && <Loader2 size={16} className="animate-spin" />}
              {creating ? 'Parsing...' : 'Parse Strategy'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 text-content-muted hover:text-content transition-colors"
            >
              Cancel
            </button>
          </div>

          {/* Parse result */}
          {parseResult && (
            <div className="mt-4 bg-surface-raised rounded-lg p-4">
              <h3 className="font-medium text-emerald-400 mb-2">Strategy Parsed Successfully</h3>
              <p className="text-sm text-content-secondary mb-2">Name: {parseResult.name}</p>
              <details>
                <summary className="text-sm text-content-muted cursor-pointer hover:text-content">
                  View parsed config (JSON)
                </summary>
                <pre className="mt-2 text-xs text-content-secondary overflow-auto max-h-64 bg-surface-card p-3 rounded">
                  {JSON.stringify(parseResult.config, null, 2)}
                </pre>
              </details>
              <p className="text-sm text-content-faint mt-2">
                Strategy is created but disabled. Enable it to start receiving signals.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Strategy list */}
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="animate-spin text-content-faint" size={32} />
        </div>
      ) : strategies.length === 0 ? (
        <div className="text-center py-12 text-content-faint">
          <p>No strategies yet. Click "New Strategy" to create one.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {strategies.map(s => (
            <StrategyCard
              key={s.id}
              strategy={s}
              onToggle={toggle}
              onDelete={remove}
              onSetAutonomy={setAutonomy}
            />
          ))}
        </div>
      )}
    </div>
  )
}
