import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, BookOpen } from 'lucide-react'
import { api } from '../api/client'

interface Param {
  type: string
  default: number | string
  description: string
}

interface Indicator {
  name: string
  full_name: string
  description: string
  custom?: boolean
  params: Record<string, Param>
  outputs: Record<string, string>
  supports_cross: boolean
  timeframes: string[]
}

export default function IndicatorPanel() {
  const [open, setOpen] = useState(false)
  const [indicators, setIndicators] = useState<Indicator[]>([])
  const [loaded, setLoaded] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    if (open && !loaded) {
      api.getIndicators().then((data) => {
        setIndicators(data)
        setLoaded(true)
      })
    }
  }, [open, loaded])

  const standard = indicators.filter((i) => !i.custom)
  const custom = indicators.filter((i) => i.custom)

  const toggleIndicator = (name: string) => {
    setExpanded(expanded === name ? null : name)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-5 py-3 text-left hover:bg-gray-800/50 transition-colors rounded-lg"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-gray-300">
          <BookOpen size={16} />
          Indicator Reference ({loaded ? indicators.length : '...'})
        </span>
        <ChevronDown
          size={16}
          className={`text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className="px-5 pb-4 space-y-4">
          {/* Standard Indicators */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Standard ({standard.length})
            </h3>
            <div className="space-y-1">
              {standard.map((ind) => (
                <IndicatorRow
                  key={ind.name}
                  indicator={ind}
                  isExpanded={expanded === ind.name}
                  onToggle={() => toggleIndicator(ind.name)}
                />
              ))}
            </div>
          </div>

          {/* Custom / SMC Indicators */}
          {custom.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Custom / SMC ({custom.length})
              </h3>
              <div className="space-y-1">
                {custom.map((ind) => (
                  <IndicatorRow
                    key={ind.name}
                    indicator={ind}
                    isExpanded={expanded === ind.name}
                    onToggle={() => toggleIndicator(ind.name)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function IndicatorRow({
  indicator,
  isExpanded,
  onToggle,
}: {
  indicator: Indicator
  isExpanded: boolean
  onToggle: () => void
}) {
  const params = Object.entries(indicator.params)
  const outputs = Object.entries(indicator.outputs)

  return (
    <div className="border border-gray-800 rounded-md">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full px-3 py-2 text-left text-sm hover:bg-gray-800/50 transition-colors rounded-md"
      >
        {isExpanded ? (
          <ChevronDown size={14} className="text-gray-500 flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-gray-500 flex-shrink-0" />
        )}
        <span className="font-medium text-brand-400">{indicator.name}</span>
        <span className="text-gray-500">{indicator.full_name}</span>
        {indicator.supports_cross && (
          <span className="ml-auto text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">
            cross
          </span>
        )}
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 pt-1 space-y-3 text-xs">
          <p className="text-gray-400">{indicator.description}</p>

          {/* Params */}
          {params.length > 0 && (
            <div>
              <h4 className="font-semibold text-gray-500 mb-1">Parameters</h4>
              <table className="w-full">
                <tbody>
                  {params.map(([key, p]) => (
                    <tr key={key} className="border-t border-gray-800/50">
                      <td className="py-1 pr-3 font-mono text-emerald-400">{key}</td>
                      <td className="py-1 pr-3 text-gray-500">{p.type}</td>
                      <td className="py-1 pr-3 text-gray-300">
                        default: <span className="text-yellow-400">{String(p.default)}</span>
                      </td>
                      <td className="py-1 text-gray-500">{p.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Outputs */}
          <div>
            <h4 className="font-semibold text-gray-500 mb-1">Outputs</h4>
            <table className="w-full">
              <tbody>
                {outputs.map(([key, desc]) => (
                  <tr key={key} className="border-t border-gray-800/50">
                    <td className="py-1 pr-3 font-mono text-brand-400">{key}</td>
                    <td className="py-1 text-gray-400">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Timeframes */}
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-gray-500 mr-1">Timeframes:</span>
            {indicator.timeframes.map((tf) => (
              <span
                key={tf}
                className="bg-gray-800 text-gray-300 px-1.5 py-0.5 rounded text-[10px] font-mono"
              >
                {tf}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
