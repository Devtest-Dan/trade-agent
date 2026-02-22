import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { Loader2 } from 'lucide-react'
import { api } from '../api/client'

// Node colors by category
const CATEGORY_COLORS: Record<string, string> = {
  entry_pattern: '#3b82f6',    // blue
  exit_signal: '#a855f7',      // purple
  regime_filter: '#06b6d4',    // cyan
  indicator_insight: '#6366f1', // indigo
  risk_insight: '#ef4444',     // red
  combination: '#ec4899',      // pink
}

// Edge colors by relationship
const EDGE_COLORS: Record<string, string> = {
  supports: '#10b981',      // green
  contradicts: '#ef4444',   // red
  refines: '#f59e0b',       // amber
  combines_with: '#a855f7', // purple
}

// Confidence -> node size
const CONFIDENCE_SIZE: Record<string, number> = {
  HIGH: 12,
  MEDIUM: 8,
  LOW: 5,
}

interface GraphNode {
  id: number
  title: string
  category: string
  confidence: string
  win_rate: number
  sample_size: number
  market_regime: string | null
  symbol: string | null
  source_type: string
  avg_pnl: number
}

interface GraphEdge {
  id: number
  source: number
  target: number
  relationship: string
  weight: number
  reason: string
}

export default function SkillGraph() {
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphEdge[] }>({ nodes: [], links: [] })
  const [loading, setLoading] = useState(true)
  const [hovered, setHovered] = useState<GraphNode | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 })

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.getFullGraph()
        const nodes = data.nodes.map((n: any) => ({
          id: n.id,
          title: n.title,
          category: n.category,
          confidence: n.confidence,
          win_rate: n.win_rate,
          sample_size: n.sample_size,
          market_regime: n.market_regime,
          symbol: n.symbol,
          source_type: n.source_type,
          avg_pnl: n.avg_pnl,
        }))
        const links = data.edges.map((e: any) => ({
          id: e.id,
          source: e.source_id,
          target: e.target_id,
          relationship: e.relationship,
          weight: e.weight,
          reason: e.reason,
        }))
        setGraphData({ nodes, links })
      } catch (e) {
        console.error('Failed to load graph:', e)
      }
      setLoading(false)
    }
    load()
  }, [])

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height: Math.max(height, 400) })
    })
    obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const size = CONFIDENCE_SIZE[node.confidence] || 6
    const color = CATEGORY_COLORS[node.category] || '#6b7280'
    const isHovered = hovered?.id === node.id
    const isSelected = selected?.id === node.id
    const isRisk = node.category === 'risk_insight'

    // Glow for hovered/selected
    if (isHovered || isSelected) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
      ctx.fillStyle = `${color}33`
      ctx.fill()
    }

    // Node circle
    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()

    // Border
    ctx.strokeStyle = isSelected ? '#ffffff' : isHovered ? '#ffffff88' : `${color}88`
    ctx.lineWidth = isSelected ? 2 : 1
    ctx.stroke()

    // Risk insight: warning triangle overlay
    if (isRisk) {
      ctx.fillStyle = '#ffffff'
      ctx.font = `${Math.max(size, 8)}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText('!', node.x, node.y)
    }

    // Label (show when zoomed in enough or hovered)
    if (globalScale > 1.5 || isHovered || isSelected) {
      const label = node.title.length > 40 ? node.title.slice(0, 37) + '...' : node.title
      const fontSize = Math.max(10 / globalScale, 3)
      ctx.font = `${fontSize}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = '#d4d4d8'
      ctx.fillText(label, node.x, node.y + size + 2)
    }
  }, [hovered, selected])

  const linkCanvasObject = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const src = link.source
    const tgt = link.target
    if (!src.x || !tgt.x) return

    const color = EDGE_COLORS[link.relationship] || '#6b7280'
    const isContra = link.relationship === 'contradicts'

    ctx.beginPath()
    if (isContra) {
      // Dashed line for contradictions
      ctx.setLineDash([4 / globalScale, 4 / globalScale])
    } else {
      ctx.setLineDash([])
    }
    ctx.moveTo(src.x, src.y)
    ctx.lineTo(tgt.x, tgt.y)
    ctx.strokeStyle = `${color}99`
    ctx.lineWidth = Math.max(link.weight * 1.5, 0.5)
    ctx.stroke()
    ctx.setLineDash([])

    // Arrow
    const angle = Math.atan2(tgt.y - src.y, tgt.x - src.x)
    const arrowLen = 5 / globalScale
    const midX = (src.x + tgt.x) / 2
    const midY = (src.y + tgt.y) / 2
    ctx.beginPath()
    ctx.moveTo(midX, midY)
    ctx.lineTo(midX - arrowLen * Math.cos(angle - Math.PI / 6), midY - arrowLen * Math.sin(angle - Math.PI / 6))
    ctx.moveTo(midX, midY)
    ctx.lineTo(midX - arrowLen * Math.cos(angle + Math.PI / 6), midY - arrowLen * Math.sin(angle + Math.PI / 6))
    ctx.strokeStyle = color
    ctx.lineWidth = 1 / globalScale
    ctx.stroke()

    // Relationship label when zoomed in
    if (globalScale > 2.5) {
      const fontSize = Math.max(8 / globalScale, 2.5)
      ctx.font = `${fontSize}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = `${color}cc`
      ctx.fillText(link.relationship, midX, midY - 4 / globalScale)
    }
  }, [])

  const activeNode = selected || hovered

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-content-faint" size={24} />
      </div>
    )
  }

  if (graphData.nodes.length === 0) {
    return (
      <div className="text-center py-16 text-content-faint">
        <p>No skills to visualize yet.</p>
        <p className="text-sm mt-1">Run backtests to build the knowledge graph.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Legend */}
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
        <div className="text-content-muted font-medium">Nodes:</div>
        {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
          <div key={cat} className="flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-content-faint">{cat.replace('_', ' ')}</span>
          </div>
        ))}
        <div className="text-content-muted font-medium ml-4">Edges:</div>
        {Object.entries(EDGE_COLORS).map(([rel, color]) => (
          <div key={rel} className="flex items-center gap-1.5">
            <span className="inline-block w-4 h-0.5" style={{ backgroundColor: color, borderBottom: rel === 'contradicts' ? '1px dashed' : 'none' }} />
            <span className="text-content-faint">{rel}</span>
          </div>
        ))}
        <div className="text-content-muted ml-4">Size = confidence</div>
      </div>

      {/* Graph + Detail panel */}
      <div className="flex gap-4">
        {/* Graph canvas */}
        <div
          ref={containerRef}
          className="flex-1 bg-surface-raised rounded-lg border border-line/40 overflow-hidden"
          style={{ minHeight: 500 }}
        >
          <ForceGraph2D
            graphData={graphData}
            width={dimensions.width}
            height={dimensions.height}
            nodeCanvasObject={nodeCanvasObject}
            linkCanvasObject={linkCanvasObject}
            onNodeHover={(node: any) => setHovered(node || null)}
            onNodeClick={(node: any) => setSelected(selected?.id === node.id ? null : node)}
            nodeId="id"
            linkSource="source"
            linkTarget="target"
            backgroundColor="transparent"
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTicks={100}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            enableNodeDrag={true}
          />
        </div>

        {/* Detail panel */}
        {activeNode && (
          <div className="w-72 shrink-0 bg-surface-raised rounded-lg border border-line/40 p-4 space-y-3 self-start">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="text-xs font-medium px-2 py-0.5 rounded-full"
                style={{ backgroundColor: `${CATEGORY_COLORS[activeNode.category]}33`, color: CATEGORY_COLORS[activeNode.category] }}
              >
                {activeNode.category.replace('_', ' ')}
              </span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                activeNode.confidence === 'HIGH' ? 'bg-emerald-500/20 text-emerald-400' :
                activeNode.confidence === 'MEDIUM' ? 'bg-amber-500/20 text-amber-400' :
                'bg-zinc-500/20 text-zinc-400'
              }`}>
                {activeNode.confidence}
              </span>
            </div>
            <div className="text-sm font-medium text-content">{activeNode.title}</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="text-content-faint">Win Rate</div>
              <div className={`font-medium ${activeNode.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                {activeNode.win_rate}%
              </div>
              <div className="text-content-faint">Sample</div>
              <div className="text-content-muted">{activeNode.sample_size} trades</div>
              <div className="text-content-faint">Avg PnL</div>
              <div className={`font-medium ${activeNode.avg_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                ${activeNode.avg_pnl}
              </div>
              {activeNode.symbol && <>
                <div className="text-content-faint">Symbol</div>
                <div className="text-content-muted">{activeNode.symbol}</div>
              </>}
              {activeNode.market_regime && <>
                <div className="text-content-faint">Regime</div>
                <div className="text-content-muted">{activeNode.market_regime}</div>
              </>}
              <div className="text-content-faint">Source</div>
              <div className="text-content-muted">{activeNode.source_type}</div>
            </div>

            {/* Connected edges */}
            {graphData.links.filter(l => {
              const sid = typeof l.source === 'object' ? (l.source as any).id : l.source
              const tid = typeof l.target === 'object' ? (l.target as any).id : l.target
              return sid === activeNode.id || tid === activeNode.id
            }).length > 0 && (
              <div>
                <div className="text-xs font-medium text-content-muted mb-1">Connections</div>
                <div className="space-y-1">
                  {graphData.links.filter(l => {
                    const sid = typeof l.source === 'object' ? (l.source as any).id : l.source
                    const tid = typeof l.target === 'object' ? (l.target as any).id : l.target
                    return sid === activeNode.id || tid === activeNode.id
                  }).map(l => {
                    const sid = typeof l.source === 'object' ? (l.source as any).id : l.source
                    const tid = typeof l.target === 'object' ? (l.target as any).id : l.target
                    const otherId = sid === activeNode.id ? tid : sid
                    const otherNode = graphData.nodes.find(n => n.id === otherId)
                    return (
                      <div
                        key={l.id}
                        className="text-xs flex items-center gap-1.5 cursor-pointer hover:text-content transition-colors"
                        onClick={() => {
                          if (otherNode) setSelected(otherNode)
                        }}
                      >
                        <span
                          className="inline-block w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: EDGE_COLORS[l.relationship] || '#6b7280' }}
                        />
                        <span className="text-content-muted">{l.relationship}</span>
                        <span className="text-content-faint truncate">
                          {otherNode ? otherNode.title.slice(0, 30) : `#${otherId}`}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
