import { useEffect, useRef, useState, useCallback } from 'react'
import {
  Upload,
  Trash2,
  Code2,
  FileText,
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  AlertCircle,
  X,
  Save,
  RotateCcw,
  BookOpen,
} from 'lucide-react'
import { useIndicatorsStore } from '../store/indicators'
import { api } from '../api/client'

export default function Indicators() {
  const { indicators, loading, error, uploadJob, fetchIndicators, uploadIndicator, pollJob, deleteIndicator, clearJob } =
    useIndicatorsStore()

  const [showUpload, setShowUpload] = useState(false)
  const [uploadName, setUploadName] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [codeViewer, setCodeViewer] = useState<{
    name: string
    source: string
    compute_py: string
    source_mq5: string
    original: string
  } | null>(null)
  const [codeTab, setCodeTab] = useState<'python' | 'mql5'>('python')
  const [saving, setSaving] = useState(false)
  const [skillViewer, setSkillViewer] = useState<{ name: string; content: string } | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchIndicators()
  }, [])

  // Poll job status
  useEffect(() => {
    if (uploadJob && (uploadJob.status === 'pending' || uploadJob.status === 'processing')) {
      pollRef.current = setInterval(() => pollJob(uploadJob.id), 2000)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [uploadJob?.id, uploadJob?.status])

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return
    setUploading(true)
    try {
      await uploadIndicator(selectedFile, uploadName || undefined)
      setSelectedFile(null)
      setUploadName('')
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch {
      // error handled by store
    }
    setUploading(false)
  }, [selectedFile, uploadName])

  const handleViewCode = useCallback(async (name: string) => {
    try {
      const code = await api.getIndicatorCode(name)
      setCodeViewer({
        name: code.name,
        source: (code as any).source || 'custom',
        compute_py: code.compute_py || '',
        source_mq5: code.source_mq5 || '',
        original: code.compute_py || '',
      })
      setCodeTab('python')
    } catch {
      // ignore
    }
  }, [])

  const handleViewSkill = useCallback(async (name: string) => {
    try {
      const detail = await api.getIndicatorDetail(name)
      if (detail.skill) {
        setSkillViewer({ name, content: detail.skill })
      } else {
        setSkillViewer({ name, content: 'No skill documentation available for this indicator.' })
      }
    } catch {
      // ignore
    }
  }, [])

  const handleSaveCode = useCallback(async () => {
    if (!codeViewer) return
    setSaving(true)
    try {
      await api.updateIndicatorCode(codeViewer.name, codeViewer.compute_py)
      setCodeViewer({ ...codeViewer, original: codeViewer.compute_py })
    } catch {
      // ignore
    }
    setSaving(false)
  }, [codeViewer])

  const handleRevert = useCallback(() => {
    if (!codeViewer) return
    setCodeViewer({ ...codeViewer, compute_py: codeViewer.original })
  }, [codeViewer])

  const builtinIndicators = indicators.filter((i) => i.source === 'builtin')
  const customIndicators = indicators.filter((i) => i.source === 'custom')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-content">Indicators</h1>
        <button
          onClick={() => setShowUpload(!showUpload)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors text-sm font-medium"
        >
          <Upload size={16} />
          Upload Indicator
          {showUpload ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Upload Panel */}
      {showUpload && (
        <div className="bg-surface-raised border border-line/40 rounded-lg p-5 space-y-4">
          <h3 className="text-sm font-medium text-content">Upload MQL5 Indicator</h3>
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-xs text-content-muted mb-1">MQL5 File</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".mq5"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="w-full text-sm text-content-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-surface-nav file:text-content hover:file:bg-surface-page"
              />
            </div>
            <div className="w-48">
              <label className="block text-xs text-content-muted mb-1">Name (optional)</label>
              <input
                type="text"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder="Auto-detect from file"
                className="w-full px-3 py-2 bg-surface-page border border-line/40 rounded-lg text-sm text-content placeholder:text-content-faint"
              />
            </div>
            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploading}
              className="px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium whitespace-nowrap"
            >
              {uploading ? 'Uploading...' : 'Process with AI'}
            </button>
          </div>

          {/* Job Status */}
          {uploadJob && (
            <div className="flex items-center gap-3 bg-surface-page rounded-lg px-4 py-3">
              {uploadJob.status === 'pending' || uploadJob.status === 'processing' ? (
                <>
                  <Loader2 size={16} className="animate-spin text-brand-500" />
                  <span className="text-sm text-content-muted">
                    {uploadJob.status === 'pending' ? 'Queued...' : 'AI is generating indicator code...'}
                  </span>
                </>
              ) : uploadJob.status === 'complete' ? (
                <>
                  <CheckCircle2 size={16} className="text-green-500" />
                  <span className="text-sm text-green-400">
                    Indicator "{uploadJob.result_name}" created successfully
                  </span>
                  <button onClick={clearJob} className="ml-auto text-content-faint hover:text-content">
                    <X size={14} />
                  </button>
                </>
              ) : (
                <>
                  <AlertCircle size={16} className="text-red-500" />
                  <span className="text-sm text-red-400">Error: {uploadJob.error}</span>
                  <button onClick={clearJob} className="ml-auto text-content-faint hover:text-content">
                    <X size={14} />
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {loading && indicators.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-content-muted">
          <Loader2 size={20} className="animate-spin mr-2" /> Loading indicators...
        </div>
      ) : (
        <>
          {/* Built-in Indicators */}
          <div>
            <h2 className="text-sm font-medium text-content-muted mb-3">
              Built-in ({builtinIndicators.length})
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {builtinIndicators.map((ind) => (
                <IndicatorCard
                  key={ind.name}
                  indicator={ind}
                  onViewCode={() => handleViewCode(ind.name)}
                  onViewSkill={() => handleViewSkill(ind.name)}
                />
              ))}
            </div>
          </div>

          {/* Custom Indicators */}
          <div>
            <h2 className="text-sm font-medium text-content-muted mb-3">
              Custom ({customIndicators.length})
            </h2>
            {customIndicators.length === 0 ? (
              <div className="bg-surface-raised border border-line/40 border-dashed rounded-lg p-8 text-center text-content-faint text-sm">
                No custom indicators yet. Upload an MQL5 file to get started.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {customIndicators.map((ind) => (
                  <IndicatorCard
                    key={ind.name}
                    indicator={ind}
                    onViewCode={() => handleViewCode(ind.name)}
                    onViewSkill={() => handleViewSkill(ind.name)}
                    onDelete={() => deleteIndicator(ind.name)}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* Code Viewer Modal */}
      {codeViewer && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6" onClick={() => setCodeViewer(null)}>
          <div className="border border-line/40 rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col shadow-2xl" style={{ background: 'rgb(var(--s-raised))' }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-line/40">
              <div className="flex items-center gap-3">
                <Code2 size={16} className="text-brand-500" />
                <span className="text-sm font-medium text-content">{codeViewer.name}</span>
                <span className="text-[10px] px-1.5 py-0.5 bg-surface-page rounded text-content-faint">
                  {codeViewer.source === 'builtin' ? 'Built-in' : 'Custom'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {/* Tabs */}
                <button
                  onClick={() => setCodeTab('python')}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    codeTab === 'python'
                      ? 'bg-brand-600/20 text-brand-400'
                      : 'text-content-muted hover:text-content'
                  }`}
                >
                  Python
                </button>
                {codeViewer.source_mq5 && (
                  <button
                    onClick={() => setCodeTab('mql5')}
                    className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                      codeTab === 'mql5'
                        ? 'bg-brand-600/20 text-brand-400'
                        : 'text-content-muted hover:text-content'
                    }`}
                  >
                    MQL5
                  </button>
                )}
                <div className="w-px h-4 bg-line/40 mx-1" />
                <button
                  onClick={() => setCodeViewer(null)}
                  className="text-content-faint hover:text-content"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto p-1">
              {codeTab === 'python' ? (
                codeViewer.source === 'custom' ? (
                  <textarea
                    value={codeViewer.compute_py}
                    onChange={(e) => setCodeViewer({ ...codeViewer, compute_py: e.target.value })}
                    className="w-full h-full min-h-[400px] bg-surface-page text-content font-mono text-xs p-4 rounded-lg border-0 resize-none focus:outline-none"
                    spellCheck={false}
                  />
                ) : (
                  <pre className="w-full h-full min-h-[400px] bg-surface-page text-content font-mono text-xs p-4 rounded-lg overflow-auto whitespace-pre">
                    {codeViewer.compute_py}
                  </pre>
                )
              ) : (
                <pre className="w-full h-full min-h-[400px] bg-surface-page text-content-muted font-mono text-xs p-4 rounded-lg overflow-auto whitespace-pre">
                  {codeViewer.source_mq5}
                </pre>
              )}
            </div>

            {codeTab === 'python' && codeViewer.source === 'custom' && (
              <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-line/40">
                <button
                  onClick={handleRevert}
                  disabled={codeViewer.compute_py === codeViewer.original}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-content-muted hover:text-content disabled:opacity-30 transition-colors"
                >
                  <RotateCcw size={13} /> Revert
                </button>
                <button
                  onClick={handleSaveCode}
                  disabled={saving || codeViewer.compute_py === codeViewer.original}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-brand-600 text-white rounded-lg text-xs font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
                >
                  <Save size={13} /> {saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Skill Viewer Modal */}
      {skillViewer && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6" onClick={() => setSkillViewer(null)}>
          <div className="border border-line/40 rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col shadow-2xl" style={{ background: 'rgb(var(--s-raised))' }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-line/40">
              <div className="flex items-center gap-3">
                <BookOpen size={16} className="text-amber-500" />
                <span className="text-sm font-medium text-content">{skillViewer.name} — Skill Doc</span>
              </div>
              <button
                onClick={() => setSkillViewer(null)}
                className="text-content-faint hover:text-content"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-5">
              <pre className="text-xs text-content-muted font-mono whitespace-pre-wrap leading-relaxed">
                {skillViewer.content}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function IndicatorCard({
  indicator,
  onViewCode,
  onViewSkill,
  onDelete,
}: {
  indicator: any
  onViewCode?: () => void
  onViewSkill?: () => void
  onDelete?: () => void
}) {
  const outputs = indicator.outputs
    ? Object.keys(indicator.outputs)
    : []
  const params = indicator.params
    ? Object.entries(indicator.params).map(([k, v]: [string, any]) => `${k}=${v.default ?? '?'}`)
    : []

  return (
    <div className="bg-surface-raised border border-line/40 rounded-lg p-4 space-y-2">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-medium text-content">{indicator.name}</h3>
          {indicator.full_name && indicator.full_name !== indicator.name && (
            <p className="text-xs text-content-faint">{indicator.full_name}</p>
          )}
        </div>
        {indicator.source === 'custom' && (
          <span className="text-[10px] px-1.5 py-0.5 bg-brand-600/20 text-brand-400 rounded font-medium">
            CUSTOM
          </span>
        )}
      </div>

      {indicator.description && (
        <p className="text-xs text-content-muted leading-relaxed line-clamp-2">
          {indicator.description}
        </p>
      )}

      {params.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {params.map((p: string) => (
            <span key={p} className="text-[10px] px-1.5 py-0.5 bg-surface-page rounded text-content-faint">
              {p}
            </span>
          ))}
        </div>
      )}

      {outputs.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {outputs.map((o: string) => (
            <span key={o} className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-400 rounded">
              {o}
            </span>
          ))}
        </div>
      )}

      {indicator.timeframes && (
        <p className="text-[10px] text-content-faint">
          {indicator.timeframes.join(', ')}
        </p>
      )}

      {/* Actions — available for all indicators */}
      <div className="flex items-center gap-2 pt-1 border-t border-line/20">
        {onViewSkill && (
          <button
            onClick={onViewSkill}
            className="flex items-center gap-1 text-xs text-content-muted hover:text-amber-400 transition-colors"
          >
            <BookOpen size={12} /> Skill
          </button>
        )}
        {onViewCode && (
          <button
            onClick={onViewCode}
            className="flex items-center gap-1 text-xs text-content-muted hover:text-brand-400 transition-colors"
          >
            <Code2 size={12} /> Code
          </button>
        )}
        {onDelete && (
          <button
            onClick={onDelete}
            className="flex items-center gap-1 text-xs text-content-muted hover:text-red-400 transition-colors ml-auto"
          >
            <Trash2 size={12} /> Delete
          </button>
        )}
      </div>
    </div>
  )
}
