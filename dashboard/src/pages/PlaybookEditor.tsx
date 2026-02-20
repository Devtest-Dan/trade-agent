import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Save, MessageSquare, X, RefreshCw, BookOpen, ChevronDown, ChevronRight } from 'lucide-react'
import { api } from '../api/client'
import PlaybookChat from '../components/PlaybookChat'

const autonomyColors: Record<string, string> = {
  signal_only: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  semi_auto: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  full_auto: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
}

function ExplanationSection({ explanation }: { explanation: string }) {
  if (!explanation) return null

  // Parse the markdown-ish explanation into sections
  const lines = explanation.split('\n')
  const elements: React.ReactNode[] = []
  let currentList: string[] = []

  const flushList = () => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`} className="space-y-1.5 ml-1">
          {currentList.map((item, i) => (
            <li key={i} className="flex gap-2 text-sm text-content-secondary">
              <span className="text-brand-400 mt-0.5 shrink-0">&bull;</span>
              <span dangerouslySetInnerHTML={{ __html: formatInline(item) }} />
            </li>
          ))}
        </ul>
      )
      currentList = []
    }
  }

  const formatInline = (text: string) => {
    // Bold: **text** → <strong>
    return text.replace(/\*\*(.+?)\*\*/g, '<strong class="text-content font-medium">$1</strong>')
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      continue
    }

    if (trimmed.startsWith('## ')) {
      flushList()
      elements.push(
        <h3 key={`h2-${elements.length}`} className="text-base font-semibold text-content mt-4 first:mt-0 mb-2 border-b border-line/30 pb-1">
          {trimmed.slice(3)}
        </h3>
      )
    } else if (trimmed.startsWith('### ')) {
      flushList()
      elements.push(
        <h4 key={`h3-${elements.length}`} className="text-sm font-semibold text-content-secondary mt-3 mb-1">
          {trimmed.slice(4)}
        </h4>
      )
    } else if (trimmed.match(/^\d+\.\s/)) {
      flushList()
      const text = trimmed.replace(/^\d+\.\s/, '')
      elements.push(
        <div key={`ol-${elements.length}`} className="flex gap-2 text-sm text-content-secondary ml-1">
          <span className="text-brand-400 font-mono shrink-0">{trimmed.match(/^(\d+)\./)?.[1]}.</span>
          <span dangerouslySetInnerHTML={{ __html: formatInline(text) }} />
        </div>
      )
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      currentList.push(trimmed.slice(2))
    } else {
      flushList()
      elements.push(
        <p key={`p-${elements.length}`} className="text-sm text-content-secondary leading-relaxed">
          <span dangerouslySetInnerHTML={{ __html: formatInline(trimmed) }} />
        </p>
      )
    }
  }
  flushList()

  return <div className="space-y-1">{elements}</div>
}

export default function PlaybookEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [playbook, setPlaybook] = useState<any>(null)
  const [configJson, setConfigJson] = useState('')
  const [saving, setSaving] = useState(false)
  const [chatOpen, setChatOpen] = useState(searchParams.get('chat') === '1')
  const [runtimeState, setRuntimeState] = useState<any>(null)
  const [loadingState, setLoadingState] = useState(false)
  const [explanationOpen, setExplanationOpen] = useState(true)

  useEffect(() => {
    if (id) {
      api.getPlaybook(Number(id)).then((p) => {
        setPlaybook(p)
        setConfigJson(JSON.stringify(p.config, null, 2))
      })
      fetchState()
    }
  }, [id])

  const fetchState = async () => {
    if (!id) return
    setLoadingState(true)
    try {
      const state = await api.getPlaybookState(Number(id))
      setRuntimeState(state)
    } catch {
      setRuntimeState(null)
    }
    setLoadingState(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const config = JSON.parse(configJson)
      await api.updatePlaybook(Number(id), { config })
      setPlaybook((prev: any) => ({ ...prev, config }))
    } catch (e: any) {
      alert('Error: ' + e.message)
    }
    setSaving(false)
  }

  const handleConfigUpdated = (config: any) => {
    setConfigJson(JSON.stringify(config, null, 2))
    setPlaybook((prev: any) => ({ ...prev, config }))
  }

  if (!playbook) return <div className="text-content-faint">Loading...</div>

  const phases = playbook.config?.phases ? Object.keys(playbook.config.phases) : []
  const currentPhase = runtimeState?.current_phase || 'idle'
  const indicators = playbook.config?.indicators || []
  const risk = playbook.config?.risk || {}
  const autonomy = playbook.config?.autonomy || 'signal_only'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/playbooks')}
            className="p-2 text-content-muted hover:text-content"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold">{playbook.name}</h1>
            <p className="text-sm text-content-faint">{playbook.description_nl}</p>
          </div>
        </div>
        <button
          onClick={() => setChatOpen(!chatOpen)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
            chatOpen
              ? 'bg-surface-raised text-content'
              : 'bg-brand-600/20 text-brand-400 hover:bg-brand-600/30'
          }`}
        >
          {chatOpen ? <X size={16} /> : <MessageSquare size={16} />}
          {chatOpen ? 'Close Chat' : 'Discuss & Refine'}
        </button>
      </div>

      {/* 2-column layout: content left, chat right */}
      <div className={`grid gap-6 ${chatOpen ? 'lg:grid-cols-[2fr_1fr]' : 'grid-cols-1'}`}>
        {/* Left column */}
        <div className="space-y-6 min-w-0">
          {/* Strategy Explanation */}
          {playbook.explanation && (
            <div className="bg-surface-card rounded-xl overflow-hidden">
              <button
                onClick={() => setExplanationOpen(!explanationOpen)}
                className="w-full flex items-center justify-between px-5 py-4 hover:bg-surface-raised/30 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <BookOpen size={18} className="text-brand-400" />
                  <h2 className="text-lg font-semibold">Strategy Explanation</h2>
                </div>
                {explanationOpen ? <ChevronDown size={18} className="text-content-muted" /> : <ChevronRight size={18} className="text-content-muted" />}
              </button>
              {explanationOpen && (
                <div className="px-5 pb-5 border-t border-line/20 pt-4">
                  <ExplanationSection explanation={playbook.explanation} />
                </div>
              )}
            </div>
          )}

          {/* Overview row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Autonomy */}
            <div className="bg-surface-card rounded-xl p-4">
              <div className="text-sm text-content-faint mb-1">Autonomy</div>
              <span className={`text-sm font-medium px-2 py-1 rounded border ${autonomyColors[autonomy] || 'bg-surface-raised text-content-muted border-line'}`}>
                {autonomy.replace('_', ' ')}
              </span>
            </div>

            {/* Symbols */}
            <div className="bg-surface-card rounded-xl p-4">
              <div className="text-sm text-content-faint mb-1">Symbols</div>
              <div className="flex flex-wrap gap-1">
                {(playbook.config?.symbols || []).map((s: string) => (
                  <span key={s} className="text-sm font-medium text-content">{s}</span>
                ))}
              </div>
            </div>

            {/* Risk */}
            <div className="bg-surface-card rounded-xl p-4">
              <div className="text-sm text-content-faint mb-1">Risk</div>
              <div className="text-sm text-content-secondary space-y-0.5">
                <div>Max lot: {risk.max_lot || '--'}</div>
                <div>Max daily: {risk.max_daily_trades || '--'}</div>
              </div>
            </div>
          </div>

          {/* Runtime state */}
          <div className="bg-surface-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold">Runtime State</h2>
              <button
                onClick={fetchState}
                disabled={loadingState}
                className="flex items-center gap-1 text-sm text-content-muted hover:text-content transition-colors"
              >
                <RefreshCw size={14} className={loadingState ? 'animate-spin' : ''} />
                Refresh
              </button>
            </div>

            {/* Phase flow visualization */}
            <div className="flex flex-wrap gap-2 mb-4">
              {phases.map((phase) => (
                <div
                  key={phase}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                    phase === currentPhase
                      ? 'bg-brand-600/20 text-brand-400 border-brand-500/40'
                      : 'bg-surface-raised text-content-faint border-line'
                  }`}
                >
                  {phase}
                  {phase === currentPhase && (
                    <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
                  )}
                </div>
              ))}
            </div>

            {runtimeState ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div>
                  <span className="text-content-faint">Phase:</span>{' '}
                  <span className="text-content">{runtimeState.current_phase}</span>
                </div>
                <div>
                  <span className="text-content-faint">Bars:</span>{' '}
                  <span className="text-content">{runtimeState.bars_in_phase || 0}</span>
                </div>
                {runtimeState.open_ticket && (
                  <div>
                    <span className="text-content-faint">Ticket:</span>{' '}
                    <span className="text-content">#{runtimeState.open_ticket}</span>
                  </div>
                )}
                {runtimeState.open_direction && (
                  <div>
                    <span className="text-content-faint">Direction:</span>{' '}
                    <span className={runtimeState.open_direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>
                      {runtimeState.open_direction}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-content-faint">
                {playbook.enabled ? 'Loading state...' : 'Enable the playbook to see runtime state.'}
              </p>
            )}

            {/* Variables */}
            {runtimeState?.variables && Object.keys(runtimeState.variables).length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-medium text-content-muted mb-2">Variables</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
                  {Object.entries(runtimeState.variables).map(([key, val]) => (
                    <div key={key} className="bg-surface-raised rounded px-2 py-1">
                      <span className="text-content-faint">{key}:</span>{' '}
                      <span className="text-content">{String(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Indicators */}
          {indicators.length > 0 && (
            <div className="bg-surface-card rounded-xl p-5">
              <h2 className="text-lg font-semibold mb-3">Indicators</h2>
              <div className="space-y-2">
                {indicators.map((ind: any, i: number) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-surface-raised/50 rounded-lg text-sm">
                    <div>
                      <span className="font-medium text-content">{ind.id}</span>
                      <span className="text-content-faint ml-2">{ind.name}</span>
                    </div>
                    <div className="flex items-center gap-3 text-content-muted">
                      <span>{ind.timeframe}</span>
                      {ind.params && Object.keys(ind.params).length > 0 && (
                        <span className="text-xs text-content-faint">
                          {Object.entries(ind.params).map(([k, v]) => `${k}=${v}`).join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Config editor */}
          <div className="bg-surface-card rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Playbook Config</h2>
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
              className="w-full h-96 px-4 py-3 bg-surface-inset border border-line rounded-lg text-content font-mono text-sm focus:outline-none focus:border-brand-500 resize-y"
              spellCheck={false}
            />
          </div>
        </div>

        {/* Right column — refinement chat */}
        {chatOpen && (
          <div className="bg-surface-card rounded-xl lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-6rem)] flex flex-col min-h-[400px]">
            <div className="px-4 py-3 border-b border-line/30">
              <h2 className="text-sm font-semibold text-content-secondary">Discuss & Refine</h2>
              <p className="text-xs text-content-faint">Chat with AI to tweak entry/exit conditions, risk, or any aspect of the strategy</p>
            </div>
            <PlaybookChat
              playbookId={Number(id)}
              onConfigUpdated={handleConfigUpdated}
            />
          </div>
        )}
      </div>
    </div>
  )
}
