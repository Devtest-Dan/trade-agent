import { useEffect } from 'react'
import { useSignalsStore } from '../store/signals'
import SignalCard from '../components/SignalCard'
import { Loader2 } from 'lucide-react'

export default function Signals() {
  const { signals, loading, fetch, approve, reject } = useSignalsStore()

  useEffect(() => {
    fetch()
    const interval = setInterval(() => fetch(), 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Signals</h1>
        <div className="flex gap-2">
          <button
            onClick={() => fetch()}
            className="px-3 py-1.5 text-sm bg-surface-raised text-content-secondary rounded hover:bg-surface-raised"
          >
            Refresh
          </button>
          <button
            onClick={() => fetch({ status: 'pending' })}
            className="px-3 py-1.5 text-sm bg-yellow-500/20 text-yellow-400 rounded hover:bg-yellow-500/30"
          >
            Pending
          </button>
          <button
            onClick={() => fetch()}
            className="px-3 py-1.5 text-sm bg-surface-raised text-content-secondary rounded hover:bg-surface-raised"
          >
            All
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="animate-spin text-content-faint" size={32} />
        </div>
      ) : signals.length === 0 ? (
        <div className="text-center py-12 text-content-faint">
          <p>No signals yet. Enable a strategy to start receiving signals.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {signals.map(s => (
            <SignalCard
              key={s.id}
              signal={s}
              onApprove={approve}
              onReject={reject}
            />
          ))}
        </div>
      )}
    </div>
  )
}
