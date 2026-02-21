import { useState, useEffect } from 'react'
import { Plus, X } from 'lucide-react'
import { api } from '../api/client'
import type { ActiveIndicator } from '../store/chart'

const OVERLAY_SET = new Set(['EMA', 'SMA', 'Bollinger', 'NW_Envelope', 'NW_RQ_Kernel', 'KeltnerChannel', 'SMC_Structure', 'OB_FVG'])

const DEFAULT_PARAMS: Record<string, Record<string, number>> = {
  RSI: { period: 14 },
  EMA: { period: 20 },
  SMA: { period: 20 },
  MACD: { fast_ema: 12, slow_ema: 26, signal: 9 },
  Stochastic: { k_period: 5, d_period: 3, slowing: 3 },
  Bollinger: { period: 20, deviation: 2.0 },
  SMC_Structure: { swing_length: 5 },
  OB_FVG: { test_percent: 30, fill_percent: 50 },
  NW_Envelope: { lookback_window: 8, relative_weighting: 8, start_bar: 25, atr_length: 60, near_factor: 1.5, far_factor: 8.0 },
  NW_RQ_Kernel: { lookback_window: 8, relative_weighting: 8, start_bar: 25 },
  ATR: { period: 14 },
  ADX: { period: 14 },
  CCI: { period: 14 },
  WilliamsR: { period: 14 },
}

interface Props {
  active: ActiveIndicator[]
  onAdd: (name: string, params: Record<string, any>) => void
  onRemove: (idx: number) => void
}

export default function IndicatorSelector({ active, onAdd, onRemove }: Props) {
  const [catalog, setCatalog] = useState<{ name: string; type: string }[]>([])
  const [showPicker, setShowPicker] = useState(false)

  useEffect(() => {
    api.listIndicators().then((list) => {
      const items = list
        .map((ind: any) => ({
          name: ind.name || ind,
          type: OVERLAY_SET.has(ind.name || ind) ? 'overlay' : 'oscillator',
        }))
        .filter(Boolean)
      setCatalog(items)
    }).catch(() => {
      // Use fallback catalog
      const names = ['RSI', 'EMA', 'SMA', 'MACD', 'Stochastic', 'Bollinger', 'ATR', 'ADX', 'CCI', 'WilliamsR']
      setCatalog(names.map((n) => ({ name: n, type: OVERLAY_SET.has(n) ? 'overlay' : 'oscillator' })))
    })
  }, [])

  const overlays = catalog.filter((c) => c.type === 'overlay')
  const oscillators = catalog.filter((c) => c.type === 'oscillator')

  function handleAdd(name: string) {
    const params = DEFAULT_PARAMS[name] || {}
    onAdd(name, { ...params })
    setShowPicker(false)
  }

  return (
    <div>
      {/* Active indicators as pills */}
      <div className="flex flex-wrap gap-2 items-center">
        {active.map((ind, idx) => (
          <span
            key={idx}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-brand-600/10 text-brand-400 border border-brand-600/20"
          >
            {ind.name}
            {Object.keys(ind.params).length > 0 && (
              <span className="text-content-faint">
                ({Object.values(ind.params).join(',')})
              </span>
            )}
            <button
              onClick={() => onRemove(idx)}
              className="ml-0.5 hover:text-red-400 transition-colors"
            >
              <X size={12} />
            </button>
          </span>
        ))}

        <button
          onClick={() => setShowPicker(!showPicker)}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-surface-raised text-content-muted hover:text-content border border-line/40 transition-colors"
        >
          <Plus size={12} />
          Add Indicator
        </button>
      </div>

      {/* Picker dropdown */}
      {showPicker && (
        <div className="mt-2 p-3 rounded-lg bg-surface-raised border border-line/40 max-w-md">
          {overlays.length > 0 && (
            <div className="mb-3">
              <div className="text-[10px] uppercase tracking-wider text-content-faint mb-1.5">Overlays</div>
              <div className="flex flex-wrap gap-1.5">
                {overlays.map((ind) => (
                  <button
                    key={ind.name}
                    onClick={() => handleAdd(ind.name)}
                    className="px-2 py-1 rounded text-xs bg-surface-page hover:bg-brand-600/10 hover:text-brand-400 text-content-muted border border-line/30 transition-colors"
                  >
                    {ind.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {oscillators.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-content-faint mb-1.5">Oscillators</div>
              <div className="flex flex-wrap gap-1.5">
                {oscillators.map((ind) => (
                  <button
                    key={ind.name}
                    onClick={() => handleAdd(ind.name)}
                    className="px-2 py-1 rounded text-xs bg-surface-page hover:bg-brand-600/10 hover:text-brand-400 text-content-muted border border-line/30 transition-colors"
                  >
                    {ind.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
