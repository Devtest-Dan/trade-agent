import { useEffect, useState, useCallback, useRef, Fragment } from 'react'
import {
  Activity, Play, Square, RefreshCw, TrendingUp, TrendingDown, Minus,
  ChevronDown, ChevronUp, Target, AlertTriangle, CheckCircle, XCircle, Clock,
} from 'lucide-react'
import { useAnalystStore } from '../store/analyst'
import { wsClient } from '../api/ws'
import { cn, formatTime, formatDate, formatPrice } from '../lib/utils'

// ── Color maps ──────────────────────────────────────────────────────────────

const biasColor: Record<string, string> = {
  bullish: 'text-emerald-400',
  bearish: 'text-red-400',
  neutral: 'text-amber-400',
}

const biasBg: Record<string, string> = {
  bullish: 'bg-emerald-500/20 text-emerald-400',
  bearish: 'bg-red-500/20 text-red-400',
  neutral: 'bg-amber-500/20 text-amber-400',
}

const urgencyColor: Record<string, string> = {
  alert: 'text-red-400',
  approach: 'text-amber-400',
  nearby: 'text-blue-400',
  coast: 'text-content-muted',
  quiet: 'text-content-faint',
}

const reviewColor: Record<string, string> = {
  agree: 'text-emerald-400',
  disagree: 'text-red-400',
  partially_agree: 'text-amber-400',
}

function BiasIcon({ bias, size = 16 }: { bias: string; size?: number }) {
  if (bias === 'bullish') return <TrendingUp size={size} className="text-emerald-400" />
  if (bias === 'bearish') return <TrendingDown size={size} className="text-red-400" />
  return <Minus size={size} className="text-amber-400" />
}

// ── Stat Card (reusable) ────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }: {
  label: string
  value: string
  sub?: string
  color?: string
}) {
  return (
    <div className="bg-surface-card shadow-card rounded-xl border border-line/30 p-5">
      <div className="text-xs text-content-faint mb-1">{label}</div>
      <div className={cn('text-xl font-bold', color || 'text-content')}>{value}</div>
      {sub && <div className="text-xs text-content-faint mt-1">{sub}</div>}
    </div>
  )
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function Analyst() {
  const {
    running, symbols, timeframes, model, perSymbol, totalOpinions,
    latestOpinions, history, accuracy, scoredOpinions,
    loading, error, selectedSymbol,
    fetchStatus, fetchLatest, fetchHistory, fetchAccuracy, fetchScored,
    start, stop, analyzeNow, scoreNow, setSelectedSymbol, handleOpinionEvent,
  } = useAnalystStore()

  const [expandedOpinion, setExpandedOpinion] = useState<string | null>(null)
  const [expandedScored, setExpandedScored] = useState<number | null>(null)
  const [expandedHistory, setExpandedHistory] = useState<number | null>(null)
  const refreshRef = useRef<number | null>(null)

  // ── Initial fetch ─────────────────────────────────────────────────────────

  const loadAll = useCallback(async () => {
    await fetchStatus()
    const status = useAnalystStore.getState()
    if (status.symbols?.length) {
      await Promise.all([
        ...status.symbols.map((s: string) => fetchLatest(s)),
        fetchAccuracy(),
        fetchScored(),
        fetchHistory(),
      ])
    }
  }, [fetchStatus, fetchLatest, fetchAccuracy, fetchScored, fetchHistory])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  // ── Auto-refresh status every 30s while running ───────────────────────────

  useEffect(() => {
    if (running) {
      refreshRef.current = window.setInterval(() => {
        fetchStatus()
        symbols?.forEach((s: string) => fetchLatest(s))
      }, 30000)
    }
    return () => {
      if (refreshRef.current) clearInterval(refreshRef.current)
    }
  }, [running, symbols, fetchStatus, fetchLatest])

  // ── WebSocket listener ────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (data: any) => {
      handleOpinionEvent(data)
    }
    wsClient.on('analyst_opinion', handler)
    return () => { wsClient.off('analyst_opinion', handler) }
  }, [handleOpinionEvent])

  // ── Derived data ──────────────────────────────────────────────────────────

  const opinionSymbols = Object.keys(latestOpinions || {})
  const accSymbols = symbols || []
  const effectiveSelected = selectedSymbol || accSymbols[0] || ''
  const accData = accuracy?.find((a: any) => a.stat_period === 'last_7d' && a.total_opinions > 0)
    || accuracy?.find((a: any) => a.stat_period === 'all_time')

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleStart = async () => { await start(); await fetchStatus() }
  const handleStop = async () => { await stop(); await fetchStatus() }
  const handleAnalyze = async () => { await analyzeNow(); setTimeout(loadAll, 2000) }
  const handleScore = async () => { await scoreNow(); setTimeout(() => { fetchScored(); fetchAccuracy() }, 2000) }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">

      {/* ── 1. Header + Controls ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Activity size={22} className="text-brand-400" />
          <h1 className="text-xl font-semibold text-content">Market Analyst</h1>
          <span className="flex items-center gap-1.5 text-sm">
            <span className={cn(
              'inline-block w-2 h-2 rounded-full',
              running ? 'bg-emerald-400 animate-pulse' : 'bg-red-400',
            )} />
            <span className="text-content-muted">{running ? 'Running' : 'Stopped'}</span>
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-3 text-xs text-content-muted">
            {symbols?.length > 0 && <span>{symbols.length} symbols</span>}
            {model && <span className="text-content-faint">{model}</span>}
            {totalOpinions > 0 && <span>{totalOpinions} opinions</span>}
          </div>

          {running ? (
            <button
              onClick={handleStop}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 text-sm hover:bg-red-500/30 transition-colors"
            >
              <Square size={14} /> Stop
            </button>
          ) : (
            <button
              onClick={handleStart}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 text-sm hover:bg-emerald-500/30 transition-colors"
            >
              <Play size={14} /> Start
            </button>
          )}

          <button
            onClick={handleAnalyze}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-600/20 text-brand-400 text-sm hover:bg-brand-600/30 transition-colors"
          >
            <RefreshCw size={14} /> Analyze Now
          </button>

          <button
            onClick={handleScore}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-400 text-sm hover:bg-amber-500/30 transition-colors"
          >
            <Target size={14} /> Score
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400 flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* Loading state */}
      {loading && !opinionSymbols.length && (
        <div className="flex items-center justify-center py-16 text-content-faint">
          <RefreshCw size={20} className="animate-spin mr-2" /> Loading analyst data...
        </div>
      )}

      {/* ── 2. Per-Symbol Opinion Cards ──────────────────────────────────── */}
      {opinionSymbols.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {opinionSymbols.map((sym) => {
            const op = latestOpinions[sym]
            if (!op) return null
            const isExpanded = expandedOpinion === sym
            const bias = op.bias || 'neutral'
            const tf = op.timeframe_analysis || {}

            return (
              <div
                key={sym}
                className="bg-surface-card shadow-card rounded-xl border border-line/30 p-5 space-y-3"
              >
                {/* Header row */}
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-content">{sym}</span>
                  <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', biasBg[bias])}>
                    {bias} {op.confidence != null ? `${op.confidence}%` : ''}
                  </span>
                </div>

                {/* Price + urgency */}
                <div className="flex items-center justify-between text-xs">
                  {op.current_price && (
                    <span className="text-content-secondary">
                      Price: {formatPrice(op.current_price, sym.includes('JPY') ? 3 : 2)}
                    </span>
                  )}
                  {op.urgency && (
                    <span className={cn(urgencyColor[op.urgency] || 'text-content-muted')}>
                      Urgency: {op.urgency}
                      {op.next_interval ? ` (${op.next_interval}s)` : ''}
                    </span>
                  )}
                </div>

                {/* Review verdict */}
                {op.review_verdict && (
                  <div className="flex items-center justify-between text-xs">
                    <span className={cn(reviewColor[op.review_verdict] || 'text-content-muted')}>
                      Review: {op.review_verdict.replace('_', ' ')}
                    </span>
                    {op.revised_confidence != null && (
                      <span className="text-content-secondary">
                        Revised conf: {op.revised_confidence}%
                      </span>
                    )}
                  </div>
                )}

                <div className="border-t border-line/30" />

                {/* Key concern */}
                {op.review_key_concern && (
                  <div className="text-xs text-content-muted">
                    <span className="text-content-secondary font-medium">Key concern: </span>
                    {op.review_key_concern}
                  </div>
                )}

                {/* Challenges (expandable) */}
                {op.review_challenges?.length > 0 && (
                  <div>
                    <button
                      onClick={() => setExpandedOpinion(isExpanded ? null : sym)}
                      className="flex items-center gap-1 text-xs text-content-muted hover:text-content transition-colors"
                    >
                      {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      Challenges ({op.review_challenges.length})
                    </button>
                    {isExpanded && (
                      <ul className="mt-1 space-y-1 pl-4">
                        {op.review_challenges.map((c: string, i: number) => (
                          <li key={i} className="text-xs text-content-faint list-disc">{c}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {/* Trade ideas */}
                {op.trade_ideas?.length > 0 && (
                  <div className="text-xs bg-surface-inset border border-line rounded-lg px-3 py-2 text-content-secondary">
                    <span className="font-medium text-content-muted">Trade: </span>
                    {`${op.trade_ideas[0].direction} ${JSON.stringify(op.trade_ideas[0].entry_zone || '')} TP=${JSON.stringify(op.trade_ideas[0].targets || '')} SL=${op.trade_ideas[0].stop_loss || ''}`}
                  </div>
                )}

                <div className="border-t border-line/30" />

                {/* Timeframe biases */}
                {Object.keys(tf).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(tf).map(([tfKey, tfBias]: [string, any]) => {
                      const b = typeof tfBias === 'string' ? tfBias : tfBias?.bias || 'neutral'
                      return (
                        <span key={tfKey} className="text-xs text-content-faint">
                          <span className="text-content-muted font-medium">{tfKey}:</span>{' '}
                          <span className={biasColor[b] || 'text-content-faint'}>{b}</span>
                        </span>
                      )
                    })}
                  </div>
                )}

                {/* Timestamp */}
                {op.timestamp && (
                  <div className="text-xs text-content-faint flex items-center gap-1">
                    <Clock size={10} /> {formatDate(op.timestamp)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── 3. Accuracy Stats Section ────────────────────────────────────── */}
      {accSymbols.length > 0 && (
        <div className="bg-surface-card shadow-card rounded-xl border border-line/30 p-5 space-y-4">
          <h2 className="text-lg font-semibold text-content flex items-center gap-2">
            <Target size={18} className="text-brand-400" />
            Accuracy Stats
          </h2>

          {/* Symbol tab bar */}
          <div className="flex flex-wrap gap-1 border-b border-line/30 pb-2">
            {accSymbols.map((sym) => (
              <button
                key={sym}
                onClick={() => setSelectedSymbol(sym)}
                className={cn(
                  'px-3 py-1.5 text-sm rounded-t-lg transition-colors',
                  effectiveSelected === sym
                    ? 'bg-brand-600/20 text-brand-400 border-b-2 border-brand-400'
                    : 'text-content-muted hover:text-content',
                )}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Stats cards grid */}
          {accData ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              <StatCard
                label="Bias Accuracy"
                value={accData.bias_accuracy != null ? `${accData.bias_accuracy.toFixed(1)}%` : '--'}
                color={accData.bias_accuracy >= 50 ? 'text-emerald-400' : 'text-red-400'}
              />
              <StatCard
                label="TP1 Rate"
                value={accData.tp1_hit_rate != null ? `${accData.tp1_hit_rate.toFixed(1)}%` : '--'}
                color="text-brand-400"
              />
              <StatCard
                label="SL Rate"
                value={accData.sl_hit_rate != null ? `${accData.sl_hit_rate.toFixed(1)}%` : '--'}
                color={accData.sl_hit_rate <= 30 ? 'text-amber-400' : 'text-red-400'}
              />
              <StatCard
                label="Avg Score"
                value={accData.avg_score != null ? accData.avg_score.toFixed(2) : '--'}
                color="text-content"
              />
              <StatCard
                label="Level Reach Rate"
                value={accData.level_reach_rate != null ? `${accData.level_reach_rate.toFixed(1)}%` : '--'}
                sub={`${accData.total_opinions || 0} scored`}
                color="text-blue-400"
              />
            </div>
          ) : (
            <div className="text-sm text-content-faint py-4 text-center">
              No accuracy data for {effectiveSelected}
            </div>
          )}
        </div>
      )}

      {/* ── 4. Recent Scored Opinions Table ──────────────────────────────── */}
      {scoredOpinions?.length > 0 && (
        <div className="bg-surface-card shadow-card rounded-xl border border-line/30 p-5 space-y-4">
          <h2 className="text-lg font-semibold text-content flex items-center gap-2">
            <CheckCircle size={18} className="text-emerald-400" />
            Recent Scored Opinions
          </h2>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-content-faint border-b border-line/30">
                  <th className="text-left py-2 px-2">Time</th>
                  <th className="text-left py-2 px-2">Symbol</th>
                  <th className="text-left py-2 px-2">Bias</th>
                  <th className="text-right py-2 px-2">Conf</th>
                  <th className="text-center py-2 px-2">Correct?</th>
                  <th className="text-center py-2 px-2">TP1</th>
                  <th className="text-center py-2 px-2">SL</th>
                  <th className="text-right py-2 px-2">Score</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {scoredOpinions.map((s: any, idx: number) => {
                  const isExp = expandedScored === idx
                  return (
                    <Fragment key={idx}>
                      <tr
                        className="border-b border-line/20 hover:bg-surface-raised/50 cursor-pointer transition-colors"
                        onClick={() => setExpandedScored(isExp ? null : idx)}
                      >
                        <td className="py-2 px-2 text-content-faint">
                          {s.timestamp ? formatTime(s.timestamp) : '--'}
                        </td>
                        <td className="py-2 px-2 text-content font-medium">{s.symbol}</td>
                        <td className={cn('py-2 px-2 font-medium', biasColor[s.bias] || 'text-content-muted')}>
                          {s.bias}
                        </td>
                        <td className="py-2 px-2 text-right text-content-secondary">
                          {s.confidence != null ? `${s.confidence}%` : '--'}
                        </td>
                        <td className="py-2 px-2 text-center">
                          {s.bias_correct === true && <CheckCircle size={14} className="text-emerald-400 inline" />}
                          {s.bias_correct === false && <XCircle size={14} className="text-red-400 inline" />}
                          {s.bias_correct == null && <Minus size={14} className="text-content-faint inline" />}
                        </td>
                        <td className="py-2 px-2 text-center">
                          {s.tp1_hit === true && <CheckCircle size={14} className="text-emerald-400 inline" />}
                          {s.tp1_hit === false && <XCircle size={14} className="text-content-faint inline" />}
                          {s.tp1_hit == null && <Minus size={14} className="text-content-faint inline" />}
                        </td>
                        <td className="py-2 px-2 text-center">
                          {s.sl_hit === true && <XCircle size={14} className="text-red-400 inline" />}
                          {s.sl_hit === false && <CheckCircle size={14} className="text-emerald-400 inline" />}
                          {s.sl_hit == null && <Minus size={14} className="text-content-faint inline" />}
                        </td>
                        <td className={cn(
                          'py-2 px-2 text-right font-bold',
                          s.score >= 0.6 ? 'text-emerald-400' : s.score >= 0.3 ? 'text-amber-400' : 'text-red-400',
                        )}>
                          {s.score != null ? s.score.toFixed(2) : '--'}
                        </td>
                        <td className="py-2 px-2">
                          {isExp
                            ? <ChevronUp size={14} className="text-content-faint" />
                            : <ChevronDown size={14} className="text-content-faint" />}
                        </td>
                      </tr>
                      {isExp && s.price_after && (
                        <tr>
                          <td colSpan={9} className="px-4 py-3 bg-surface-raised/30">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                              {Object.entries(s.price_after).map(([period, data]: [string, any]) => (
                                <div key={period} className="bg-surface-inset border border-line rounded-lg px-3 py-2">
                                  <div className="text-content-faint font-medium mb-1">{period}</div>
                                  {typeof data === 'object' && data !== null ? (
                                    <>
                                      <div className="text-content-secondary">
                                        Price: {data.price != null ? formatPrice(data.price) : '--'}
                                      </div>
                                      <div className={cn(
                                        data.pips > 0 ? 'text-emerald-400' : data.pips < 0 ? 'text-red-400' : 'text-content-faint',
                                      )}>
                                        {data.pips != null ? `${data.pips > 0 ? '+' : ''}${data.pips.toFixed(1)} pips` : ''}
                                      </div>
                                    </>
                                  ) : (
                                    <div className="text-content-secondary">{String(data)}</div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 5. History Timeline ──────────────────────────────────────────── */}
      {history?.length > 0 && (
        <div className="bg-surface-card shadow-card rounded-xl border border-line/30 p-5 space-y-4">
          <h2 className="text-lg font-semibold text-content flex items-center gap-2">
            <Clock size={18} className="text-brand-400" />
            Opinion History
          </h2>

          <div className="max-h-[500px] overflow-y-auto space-y-2 pr-1">
            {history.map((entry: any, idx: number) => {
              const isExp = expandedHistory === idx
              const bias = entry.bias || 'neutral'
              return (
                <div
                  key={idx}
                  className="bg-surface-raised rounded-lg border border-line/40 overflow-hidden"
                >
                  <button
                    onClick={() => setExpandedHistory(isExp ? null : idx)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-raised/80 transition-colors"
                  >
                    <BiasIcon bias={bias} size={16} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-content">{entry.symbol}</span>
                        <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', biasBg[bias])}>
                          {bias} {entry.confidence != null ? `${entry.confidence}%` : ''}
                        </span>
                        {entry.urgency && (
                          <span className={cn('text-xs', urgencyColor[entry.urgency] || 'text-content-faint')}>
                            {entry.urgency}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-xs text-content-faint shrink-0">
                      {entry.timestamp ? formatDate(entry.timestamp) : ''}
                    </span>
                    {isExp
                      ? <ChevronUp size={14} className="text-content-faint" />
                      : <ChevronDown size={14} className="text-content-faint" />}
                  </button>

                  {isExp && (
                    <div className="border-t border-line/40 px-4 py-3 space-y-2">
                      {entry.key_concern && (
                        <div className="text-xs text-content-muted">
                          <span className="font-medium text-content-secondary">Key concern: </span>
                          {entry.key_concern}
                        </div>
                      )}
                      {entry.trade_suggestion && (
                        <div className="text-xs bg-surface-inset border border-line rounded-lg px-3 py-2 text-content-secondary">
                          <span className="font-medium text-content-muted">Trade: </span>
                          {typeof entry.trade_suggestion === 'string'
                            ? entry.trade_suggestion
                            : JSON.stringify(entry.trade_suggestion)}
                        </div>
                      )}
                      {entry.review_verdict && (
                        <div className="text-xs">
                          <span className="text-content-faint">Review: </span>
                          <span className={reviewColor[entry.review_verdict] || 'text-content-muted'}>
                            {entry.review_verdict.replace('_', ' ')}
                          </span>
                          {entry.revised_confidence != null && (
                            <span className="text-content-faint ml-2">
                              (revised: {entry.revised_confidence}%)
                            </span>
                          )}
                        </div>
                      )}
                      {entry.challenges?.length > 0 && (
                        <div>
                          <div className="text-xs text-content-faint font-medium mb-1">Challenges:</div>
                          <ul className="space-y-0.5 pl-4">
                            {entry.challenges.map((c: string, ci: number) => (
                              <li key={ci} className="text-xs text-content-faint list-disc">{c}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {entry.timeframe_biases && Object.keys(entry.timeframe_biases).length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {Object.entries(entry.timeframe_biases).map(([tf, b]: [string, any]) => {
                            const tfBias = typeof b === 'string' ? b : b?.bias || 'neutral'
                            return (
                              <span key={tf} className="text-xs text-content-faint">
                                <span className="text-content-muted font-medium">{tf}:</span>{' '}
                                <span className={biasColor[tfBias] || 'text-content-faint'}>{tfBias}</span>
                              </span>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && opinionSymbols.length === 0 && !error && (
        <div className="text-center py-16 text-content-faint">
          <Activity size={40} className="mx-auto mb-3 opacity-30" />
          <p>No analyst opinions yet.</p>
          <p className="text-sm mt-1">
            {running
              ? 'Waiting for the first analysis cycle...'
              : 'Click Start to begin analyzing symbols.'}
          </p>
        </div>
      )}
    </div>
  )
}
