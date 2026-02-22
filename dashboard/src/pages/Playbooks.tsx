import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import { usePlaybooksStore } from '../store/playbooks'
import PlaybookCard from '../components/PlaybookCard'
import IndicatorPanel from '../components/IndicatorPanel'

export default function Playbooks() {
  const { playbooks, loading, fetch, build, toggle, remove } = usePlaybooksStore()
  const [showCreate, setShowCreate] = useState(false)
  const [description, setDescription] = useState('')
  const [building, setBuilding] = useState(false)
  const navigate = useNavigate()

  useEffect(() => { fetch() }, [])

  const handleCreateShadow = async (id: number) => {
    try {
      await api.createShadow(id)
      fetch()
    } catch (e: any) {
      alert(e.message)
    }
  }

  const handlePromoteShadow = async (id: number) => {
    if (!confirm('Promote this shadow? The parent playbook config will be replaced.')) return
    try {
      await api.promoteShadow(id)
      fetch()
    } catch (e: any) {
      alert(e.message)
    }
  }

  const handleBuild = async () => {
    if (!description.trim()) return
    setBuilding(true)
    try {
      const result = await build(description)
      setDescription('')
      setShowCreate(false)
      // Navigate to the editor with chat open for immediate discussion
      if (result?.id) {
        navigate(`/playbooks/${result.id}?chat=1`)
      }
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
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus size={18} /> New Playbook
        </button>
      </div>

      {/* Indicator reference */}
      <IndicatorPanel />

      {/* Build playbook panel */}
      {showCreate && (
        <div className="bg-surface-card rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-3">Describe Your Strategy</h2>
          <p className="text-sm text-content-muted mb-4">
            Describe your trading strategy in natural language. The AI will build a multi-phase execution playbook with entry/exit conditions, position management, and generate a full explanation of the logic.
          </p>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Example: On H1, wait for price to enter the OTE zone with bullish SMC structure. Switch to M15, enter long when RSI crosses above 40 and price closes above the FVG upper boundary. Set SL below the swing low, TP at 2R. Trail stop at 1.5 ATR after 1R profit."
            className="w-full h-36 px-4 py-3 bg-surface-inset border border-line rounded-lg text-content placeholder-content-muted focus:outline-none focus:border-brand-500 resize-none"
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
              className="px-4 py-2 text-content-muted hover:text-content transition-colors"
            >
              Cancel
            </button>
          </div>
          {building && (
            <p className="text-sm text-content-faint mt-3">
              The AI is generating your playbook and a detailed strategy explanation. This may take a minute...
            </p>
          )}
        </div>
      )}

      {/* Playbook list */}
      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="animate-spin text-content-faint" size={32} />
        </div>
      ) : playbooks.length === 0 ? (
        <div className="text-center py-12 text-content-faint">
          <p>No playbooks yet. Click "New Playbook" to build one with AI.</p>
          <p className="text-sm mt-2 text-content-faint">
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
              onCreateShadow={handleCreateShadow}
              onPromoteShadow={handlePromoteShadow}
            />
          ))}
        </div>
      )}
    </div>
  )
}
