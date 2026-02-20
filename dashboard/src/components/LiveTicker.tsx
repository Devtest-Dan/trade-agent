import { useMarketStore } from '../store/market'

export default function LiveTicker() {
  const ticks = useMarketStore((s) => s.ticks)
  const entries = Object.entries(ticks)

  if (entries.length === 0) return null

  return (
    <div className="flex items-center gap-4 text-sm">
      {entries.map(([symbol, data]) => (
        <div key={symbol} className="flex items-center gap-2">
          <span className="text-content-muted">{symbol}</span>
          <span className="text-emerald-400 font-mono">{data.bid.toFixed(2)}</span>
          <span className="text-content-faint">/</span>
          <span className="text-red-400 font-mono">{data.ask.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}
