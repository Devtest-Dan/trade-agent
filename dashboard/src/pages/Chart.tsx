import { useEffect, useRef } from 'react'
import { CandlestickChart as CandlestickIcon, Upload, RefreshCw, Loader2 } from 'lucide-react'
import { useChartStore } from '../store/chart'
import CandlestickChart from '../components/CandlestickChart'
import IndicatorSelector from '../components/IndicatorSelector'

const SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD']
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']

export default function Chart() {
  const {
    symbol, timeframe, barCount, activeIndicators,
    bars, indicatorData, loading, error,
    setSymbol, setTimeframe, setBarCount,
    addIndicator, removeIndicator, fetchData, uploadCSV,
  } = useChartStore()

  const fileRef = useRef<HTMLInputElement>(null)

  // Auto-fetch whenever symbol, timeframe, barCount, or indicators change
  useEffect(() => {
    fetchData()
  }, [symbol, timeframe, barCount, activeIndicators])

  async function handleUpload() {
    fileRef.current?.click()
  }

  async function onFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const count = await uploadCSV(file)
    if (count > 0) {
      await fetchData()
    }
    // Reset input
    if (fileRef.current) fileRef.current.value = ''
  }

  function handleAddIndicator(name: string, params: Record<string, any>) {
    addIndicator(name, params)
  }

  function handleRemoveIndicator(idx: number) {
    removeIndicator(idx)
  }

  return (
    <div className="space-y-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3">
        <CandlestickIcon size={20} className="text-brand-500" />
        <h1 className="text-lg font-semibold text-content">Chart</h1>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Symbol */}
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="px-3 py-1.5 rounded-lg text-sm bg-surface-raised border border-line/40 text-content focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        {/* Timeframe */}
        <select
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value)}
          className="px-3 py-1.5 rounded-lg text-sm bg-surface-raised border border-line/40 text-content focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          {TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>{tf}</option>
          ))}
        </select>

        {/* Bar count */}
        <input
          type="number"
          value={barCount}
          onChange={(e) => setBarCount(Math.max(10, Number(e.target.value)))}
          min={10}
          max={5000}
          className="w-20 px-3 py-1.5 rounded-lg text-sm bg-surface-raised border border-line/40 text-content focus:outline-none focus:ring-1 focus:ring-brand-500"
        />

        {/* Load from MT5 */}
        <button
          onClick={() => fetchData()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-brand-600 hover:bg-brand-700 text-white disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Load
        </button>

        {/* Upload CSV */}
        <button
          onClick={handleUpload}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-surface-raised hover:bg-surface-page text-content border border-line/40 disabled:opacity-50 transition-colors"
        >
          <Upload size={14} />
          Upload CSV/HST
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.hst"
          onChange={onFileSelected}
          className="hidden"
        />
      </div>

      {/* Indicator selector */}
      <IndicatorSelector
        active={activeIndicators}
        onAdd={handleAddIndicator}
        onRemove={handleRemoveIndicator}
      />

      {/* Error */}
      {error && (
        <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Chart area */}
      <div className="flex-1 min-h-0 rounded-lg bg-surface-raised border border-line/40 overflow-hidden" style={{ minHeight: 400 }}>
        {loading && bars.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={24} className="animate-spin text-brand-500" />
          </div>
        ) : (
          <CandlestickChart bars={bars} indicators={indicatorData} />
        )}
      </div>
    </div>
  )
}
