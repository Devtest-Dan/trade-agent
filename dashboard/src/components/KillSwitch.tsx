import { useState } from 'react'
import { OctagonX } from 'lucide-react'
import { api } from '../api/client'

export default function KillSwitch() {
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleClick = async () => {
    if (!confirming) {
      setConfirming(true)
      setTimeout(() => setConfirming(false), 3000)
      return
    }
    setLoading(true)
    try {
      const result = await api.killSwitch()
      alert(`Kill switch activated. ${result.positions_closed} positions closed, ${result.strategies_paused} strategies paused.`)
    } catch (e: any) {
      alert('Kill switch failed: ' + e.message)
    }
    setLoading(false)
    setConfirming(false)
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold text-sm transition-all ${
        confirming
          ? 'bg-red-600 text-white animate-pulse'
          : 'bg-red-600/20 text-red-400 hover:bg-red-600/40'
      }`}
    >
      <OctagonX size={18} />
      {loading ? 'Killing...' : confirming ? 'CONFIRM KILL' : 'KILL SWITCH'}
    </button>
  )
}
