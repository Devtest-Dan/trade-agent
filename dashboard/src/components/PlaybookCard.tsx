import { Play, Pause, Trash2, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

interface Props {
  playbook: any
  onToggle: (id: number) => void
  onDelete: (id: number) => void
}

const autonomyColors: Record<string, string> = {
  signal_only: 'bg-blue-500/20 text-blue-400',
  semi_auto: 'bg-yellow-500/20 text-yellow-400',
  full_auto: 'bg-emerald-500/20 text-emerald-400',
}

export default function PlaybookCard({ playbook, onToggle, onDelete }: Props) {
  return (
    <div className={`bg-surface-card rounded-lg p-4 ${playbook.enabled ? 'border border-emerald-800' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => onToggle(playbook.id)}
            className={`p-2 rounded-lg ${playbook.enabled ? 'bg-emerald-600/20 text-emerald-400' : 'bg-surface-raised text-content-faint'}`}
          >
            {playbook.enabled ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <div>
            <h3 className="font-medium text-content">{playbook.name}</h3>
            <p className="text-sm text-content-faint">
              {playbook.symbols?.join(', ')} &middot; {playbook.phases?.length || 0} phases
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium px-2 py-1 rounded ${autonomyColors[playbook.autonomy] || 'bg-surface-raised text-content-muted'}`}>
            {playbook.autonomy?.replace('_', ' ') || 'signal only'}
          </span>

          <button
            onClick={() => onDelete(playbook.id)}
            className="p-2 text-content-faint hover:text-red-400 transition-colors"
          >
            <Trash2 size={14} />
          </button>

          <Link
            to={`/playbooks/${playbook.id}`}
            className="p-2 text-content-faint hover:text-content-secondary transition-colors"
          >
            <ChevronRight size={14} />
          </Link>
        </div>
      </div>

      <p className="text-sm text-content-muted line-clamp-2">{playbook.description_nl}</p>

      {/* Explanation preview */}
      {playbook.explanation && (
        <p className="text-xs text-content-faint mt-2 line-clamp-2 italic">
          {playbook.explanation.replace(/^##?\s.+$/gm, '').replace(/[*#\-]/g, '').trim().slice(0, 200)}
        </p>
      )}

      {/* Phase pills */}
      {playbook.phases && playbook.phases.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {playbook.phases.map((phase: string) => (
            <span key={phase} className="text-[11px] px-2 py-0.5 rounded bg-surface-raised text-content-muted">
              {phase}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
