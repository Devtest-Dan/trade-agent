import { Check, X } from 'lucide-react'
import { directionColor, statusColor, formatDate } from '../lib/utils'

interface Props {
  signal: any
  onApprove?: (id: number) => void
  onReject?: (id: number) => void
}

export default function SignalCard({ signal, onApprove, onReject }: Props) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className={`font-bold text-lg ${directionColor(signal.direction)}`}>
            {signal.direction}
          </span>
          <span className="text-content-secondary font-medium">{signal.symbol}</span>
          <span className="text-content-faint text-sm">@ {signal.price_at_signal?.toFixed(2)}</span>
        </div>
        <span className={`px-2 py-1 rounded text-xs font-medium ${statusColor(signal.status)}`}>
          {signal.status}
        </span>
      </div>

      <div className="text-sm text-content-muted mb-2">
        {signal.strategy_name} &middot; {signal.created_at ? formatDate(signal.created_at) : ''}
      </div>

      {signal.ai_reasoning && (
        <p className="text-sm text-content-secondary mt-2 bg-surface-raised rounded p-2">
          {signal.ai_reasoning}
        </p>
      )}

      {signal.status === 'pending' && onApprove && onReject && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onApprove(signal.id)}
            className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600/20 text-emerald-400 rounded hover:bg-emerald-600/40 text-sm"
          >
            <Check size={14} /> Approve
          </button>
          <button
            onClick={() => onReject(signal.id)}
            className="flex items-center gap-1 px-3 py-1.5 bg-red-600/20 text-red-400 rounded hover:bg-red-600/40 text-sm"
          >
            <X size={14} /> Reject
          </button>
        </div>
      )}
    </div>
  )
}
