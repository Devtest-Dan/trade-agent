import { useEffect, useState, useCallback, lazy, Suspense } from 'react'
import { Lightbulb, Search, ChevronDown, ChevronUp, Loader2, Trash2, Link, List, GitFork } from 'lucide-react'
import { api } from '../api/client'

const SkillGraph = lazy(() => import('../components/SkillGraph'))

const CATEGORIES = [
  { value: '', label: 'All Categories' },
  { value: 'entry_pattern', label: 'Entry Pattern' },
  { value: 'exit_signal', label: 'Exit Signal' },
  { value: 'regime_filter', label: 'Regime Filter' },
  { value: 'indicator_insight', label: 'Indicator Insight' },
  { value: 'risk_insight', label: 'Risk Insight' },
  { value: 'combination', label: 'Combination' },
]

const CONFIDENCES = [
  { value: '', label: 'All Confidence' },
  { value: 'HIGH', label: 'HIGH' },
  { value: 'MEDIUM', label: 'MEDIUM' },
  { value: 'LOW', label: 'LOW' },
]

const confidenceColor: Record<string, string> = {
  HIGH: 'bg-emerald-500/20 text-emerald-400',
  MEDIUM: 'bg-amber-500/20 text-amber-400',
  LOW: 'bg-zinc-500/20 text-zinc-400',
}

const categoryColor: Record<string, string> = {
  entry_pattern: 'bg-blue-500/20 text-blue-400',
  exit_signal: 'bg-purple-500/20 text-purple-400',
  regime_filter: 'bg-cyan-500/20 text-cyan-400',
  indicator_insight: 'bg-indigo-500/20 text-indigo-400',
  risk_insight: 'bg-red-500/20 text-red-400',
  combination: 'bg-pink-500/20 text-pink-400',
}

export default function Knowledge() {
  const [skills, setSkills] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [view, setView] = useState<'list' | 'graph'>('graph')

  // Filters
  const [category, setCategory] = useState('')
  const [confidence, setConfidence] = useState('')
  const [symbol, setSymbol] = useState('')
  const [regime, setRegime] = useState('')
  const [search, setSearch] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [skillsData, statsData] = await Promise.all([
        api.listSkills({
          category: category || undefined,
          confidence: confidence || undefined,
          symbol: symbol || undefined,
          market_regime: regime || undefined,
          search: search || undefined,
        }),
        api.getKnowledgeStats(),
      ])
      setSkills(skillsData)
      setStats(statsData)
    } catch (e) {
      console.error('Failed to load knowledge:', e)
    }
    setLoading(false)
  }, [category, confidence, symbol, regime, search])

  useEffect(() => { fetchData() }, [fetchData])

  const handleExpand = async (id: number) => {
    if (expanded === id) {
      setExpanded(null)
      setDetail(null)
      return
    }
    setExpanded(id)
    try {
      const data = await api.getSkill(id)
      setDetail(data)
    } catch (e) {
      console.error('Failed to load skill detail:', e)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this skill node?')) return
    try {
      await api.deleteSkill(id)
      setSkills(skills.filter(s => s.id !== id))
      if (expanded === id) {
        setExpanded(null)
        setDetail(null)
      }
    } catch (e: any) {
      alert('Delete failed: ' + e.message)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Lightbulb size={22} className="text-amber-400" />
          <h1 className="text-xl font-semibold text-content">Knowledge Graph</h1>
        </div>
        <div className="flex items-center gap-4">
          {stats && (
            <div className="flex items-center gap-4 text-sm text-content-muted">
              <span>{stats.total} skills</span>
              <span className="text-emerald-400">{stats.by_confidence?.HIGH || 0} HIGH</span>
              <span className="text-amber-400">{stats.by_confidence?.MEDIUM || 0} MED</span>
              <span className="text-zinc-400">{stats.by_confidence?.LOW || 0} LOW</span>
            </div>
          )}
          {/* View toggle */}
          <div className="flex rounded-lg border border-line/40 overflow-hidden">
            <button
              onClick={() => setView('graph')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
                view === 'graph' ? 'bg-brand-600/20 text-brand-400' : 'text-content-muted hover:text-content'
              }`}
            >
              <GitFork size={14} /> Graph
            </button>
            <button
              onClick={() => setView('list')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
                view === 'list' ? 'bg-brand-600/20 text-brand-400' : 'text-content-muted hover:text-content'
              }`}
            >
              <List size={14} /> List
            </button>
          </div>
        </div>
      </div>

      {/* Graph View */}
      {view === 'graph' && (
        <Suspense fallback={
          <div className="flex items-center justify-center py-20">
            <Loader2 className="animate-spin text-content-faint" size={24} />
          </div>
        }>
          <SkillGraph />
        </Suspense>
      )}

      {/* List View */}
      {view === 'list' && (
        <>
          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-surface-raised text-content text-sm border border-line/40"
            >
              {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <select
              value={confidence}
              onChange={(e) => setConfidence(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-surface-raised text-content text-sm border border-line/40"
            >
              {CONFIDENCES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="Symbol..."
              className="px-3 py-1.5 rounded-lg bg-surface-raised text-content text-sm border border-line/40 w-28"
            />
            <input
              type="text"
              value={regime}
              onChange={(e) => setRegime(e.target.value)}
              placeholder="Regime..."
              className="px-3 py-1.5 rounded-lg bg-surface-raised text-content text-sm border border-line/40 w-28"
            />
            <div className="relative flex-1 min-w-[200px]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-content-faint" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search skills..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-surface-raised text-content text-sm border border-line/40"
              />
            </div>
          </div>

          {/* Skills Grid */}
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="animate-spin text-content-faint" size={24} />
            </div>
          ) : skills.length === 0 ? (
            <div className="text-center py-16 text-content-faint">
              <Lightbulb size={40} className="mx-auto mb-3 opacity-30" />
              <p>No skill nodes found.</p>
              <p className="text-sm mt-1">Run a backtest and click "Extract Skills" to generate insights.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {skills.map((skill) => (
                <div
                  key={skill.id}
                  className="bg-surface-raised rounded-lg border border-line/40 overflow-hidden"
                >
                  {/* Card header */}
                  <button
                    onClick={() => handleExpand(skill.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-raised/80 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${categoryColor[skill.category] || 'bg-zinc-500/20 text-zinc-400'}`}>
                          {skill.category?.replace('_', ' ')}
                        </span>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${confidenceColor[skill.confidence] || ''}`}>
                          {skill.confidence}
                        </span>
                        {skill.market_regime && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-surface-page text-content-muted">
                            {skill.market_regime}
                          </span>
                        )}
                        {skill.symbol && (
                          <span className="text-xs text-content-faint">{skill.symbol}</span>
                        )}
                      </div>
                      <div className="text-sm font-medium text-content truncate">{skill.title}</div>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-content-muted shrink-0">
                      <span>WR: {skill.win_rate}%</span>
                      <span>n={skill.sample_size}</span>
                      {skill.avg_rr !== 0 && <span>RR: {skill.avg_rr}</span>}
                    </div>
                    {expanded === skill.id ? <ChevronUp size={16} className="text-content-faint" /> : <ChevronDown size={16} className="text-content-faint" />}
                  </button>

                  {/* Expanded detail */}
                  {expanded === skill.id && detail && (
                    <div className="border-t border-line/40 px-4 py-3 space-y-3">
                      <pre className="text-xs text-content-muted whitespace-pre-wrap font-mono bg-surface-page rounded p-3">
                        {detail.description}
                      </pre>

                      {/* Indicator ranges */}
                      {detail.indicators_json && Object.keys(detail.indicators_json).length > 0 && (
                        <div>
                          <div className="text-xs font-medium text-content-muted mb-1">Indicator Ranges</div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {Object.entries(detail.indicators_json).map(([name, ranges]: [string, any]) => (
                              <div key={name} className="text-xs text-content-faint bg-surface-page rounded px-2 py-1">
                                <span className="text-content-muted font-medium">{name}</span>: {ranges.all_min}..{ranges.all_max}
                                {ranges.win_mean !== undefined && (
                                  <span className="text-emerald-400 ml-1">(winners: {ranges.win_mean})</span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Related skills */}
                      {detail.edges?.length > 0 && (
                        <div>
                          <div className="text-xs font-medium text-content-muted mb-1">Related Skills ({detail.edges.length})</div>
                          <div className="space-y-1">
                            {detail.edges.map((edge: any) => (
                              <div key={edge.id} className="flex items-center gap-2 text-xs text-content-faint">
                                <Link size={10} />
                                <span className="text-content-muted">{edge.relationship}</span>
                                <span>node #{edge.source_id === detail.id ? edge.target_id : edge.source_id}</span>
                                {edge.reason && <span className="text-content-faint">— {edge.reason}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Meta + actions */}
                      <div className="flex items-center justify-between pt-1">
                        <div className="flex items-center gap-3 text-xs text-content-faint">
                          {detail.source_type === 'backtest' && detail.source_id && (
                            <span>Backtest #{detail.source_id}</span>
                          )}
                          {detail.playbook_id && <span>Playbook #{detail.playbook_id}</span>}
                          {detail.timeframe && <span>{detail.timeframe}</span>}
                        </div>
                        <button
                          onClick={() => handleDelete(skill.id)}
                          className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
