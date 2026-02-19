import { Play, Pause, Trash2, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

interface Props {
  strategy: any
  onToggle: (id: number) => void
  onDelete: (id: number) => void
  onSetAutonomy: (id: number, autonomy: string) => void
}

const autonomyLabels: Record<string, string> = {
  signal_only: 'Signal Only',
  semi_auto: 'Semi-Auto',
  full_auto: 'Full Auto',
}

const autonomyColors: Record<string, string> = {
  signal_only: 'bg-blue-500/20 text-blue-400',
  semi_auto: 'bg-yellow-500/20 text-yellow-400',
  full_auto: 'bg-emerald-500/20 text-emerald-400',
}

export default function StrategyCard({ strategy, onToggle, onDelete, onSetAutonomy }: Props) {
  return (
    <div className={`bg-gray-900 border rounded-lg p-4 ${strategy.enabled ? 'border-emerald-800' : 'border-gray-800'}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => onToggle(strategy.id)}
            className={`p-2 rounded-lg ${strategy.enabled ? 'bg-emerald-600/20 text-emerald-400' : 'bg-gray-800 text-gray-500'}`}
          >
            {strategy.enabled ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <div>
            <h3 className="font-medium text-gray-100">{strategy.name}</h3>
            <p className="text-sm text-gray-500">
              {strategy.symbols?.join(', ')} &middot; {strategy.timeframes?.join(', ')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={strategy.autonomy}
            onChange={(e) => onSetAutonomy(strategy.id, e.target.value)}
            className={`text-xs font-medium px-2 py-1 rounded border-0 cursor-pointer ${autonomyColors[strategy.autonomy] || 'bg-gray-800 text-gray-400'}`}
          >
            <option value="signal_only">Signal Only</option>
            <option value="semi_auto">Semi-Auto</option>
            <option value="full_auto">Full Auto</option>
          </select>

          <button
            onClick={() => onDelete(strategy.id)}
            className="p-2 text-gray-500 hover:text-red-400 transition-colors"
          >
            <Trash2 size={14} />
          </button>

          <Link
            to={`/strategies/${strategy.id}`}
            className="p-2 text-gray-500 hover:text-gray-300 transition-colors"
          >
            <ChevronRight size={14} />
          </Link>
        </div>
      </div>

      <p className="text-sm text-gray-400 line-clamp-2">{strategy.description}</p>
    </div>
  )
}
