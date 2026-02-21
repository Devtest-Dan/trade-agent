import { useEffect, useRef } from 'react'
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from 'lightweight-charts'
import { useThemeStore } from '../store/theme'

interface MarkerData {
  bar: number
  price: number
  label: string
  color: string
  position: 'aboveBar' | 'belowBar'
}

interface IndicatorData {
  name: string
  params: Record<string, any>
  type: 'overlay' | 'oscillator'
  outputs: Record<string, (number | null)[]>
  markers?: MarkerData[]
}

interface Props {
  bars: { time: number; open: number; high: number; low: number; close: number; volume: number }[]
  indicators: Record<string, IndicatorData>
}

const OVERLAY_COLORS = ['#2196F3', '#FF9800', '#E91E63', '#4CAF50', '#9C27B0', '#00BCD4']
const OSCILLATOR_COLORS = ['#FFD600', '#FF5722', '#8BC34A', '#03A9F4', '#E040FB']

// Frontend-authoritative overlay classification (don't rely on backend type field)
const OVERLAY_SET = new Set([
  'EMA', 'SMA', 'Bollinger', 'NW_Envelope', 'NW_RQ_Kernel', 'KeltnerChannel', 'SMC_Structure', 'OB_FVG', 'TPO',
])

// Outputs that shouldn't be rendered as price-level overlay lines
const META_OUTPUTS = new Set([
  'is_bullish', 'is_bearish', 'smooth_bullish', 'smooth_bearish',
  // SMC_Structure — all outputs rendered as markers, not lines
  'trend', 'zone', 'bos_bull', 'bos_bear', 'choch_bull', 'choch_bear', 'choch_bull_level', 'choch_bear_level',
  'strong_high', 'strong_low', 'ref_high', 'ref_low',
  'equilibrium', 'ote_top', 'ote_bottom',
  'swing_high', 'swing_low',
  // OB_FVG — all outputs rendered as markers, not lines
  'ob_upper', 'ob_lower', 'ob_type', 'ob_state',
  'fvg_upper', 'fvg_lower', 'fvg_filled',
  'bull_ob_count', 'bear_ob_count', 'bull_breaker_count', 'bear_breaker_count',
])

export default function CandlestickChart({ bars, indicators }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mainChartRef = useRef<IChartApi | null>(null)
  const subChartsRef = useRef<IChartApi[]>([])
  const { dark } = useThemeStore()

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return

    // Cleanup previous charts
    cleanup()

    const container = containerRef.current
    const bg = dark ? '#0b1026' : '#ffffff'
    const textColor = dark ? '#9ca3af' : '#6b7280'
    const gridColor = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.06)'

    // Collect overlay vs oscillator indicators (use frontend OVERLAY_SET, not backend type)
    const overlays: [string, IndicatorData][] = []
    const oscillators: [string, IndicatorData][] = []
    for (const [key, ind] of Object.entries(indicators)) {
      if (OVERLAY_SET.has(ind.name)) overlays.push([key, ind])
      else oscillators.push([key, ind])
    }

    const oscHeight = 120
    const mainHeight = container.clientHeight - oscillators.length * oscHeight
    if (mainHeight < 200) return

    // Create main chart wrapper
    const mainWrapper = document.createElement('div')
    mainWrapper.style.height = `${mainHeight}px`
    container.appendChild(mainWrapper)

    const mainChart = createChart(mainWrapper, {
      width: container.clientWidth,
      height: mainHeight,
      layout: { background: { type: ColorType.Solid, color: bg }, textColor },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: gridColor },
      timeScale: { borderColor: gridColor, timeVisible: true, secondsVisible: false },
    })
    mainChartRef.current = mainChart

    // Candlestick series
    const candleSeries = mainChart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    })

    const candleData: CandlestickData<Time>[] = bars.map((b) => ({
      time: b.time as Time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }))
    candleSeries.setData(candleData)

    // Volume series on main chart
    const volumeSeries = mainChart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    mainChart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    })
    const volumeData: HistogramData<Time>[] = bars.map((b) => ({
      time: b.time as Time,
      value: b.volume,
      color: b.close >= b.open ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)',
    }))
    volumeSeries.setData(volumeData)

    // Overlay indicators on main chart (skip boolean/flag outputs)
    overlays.forEach(([_key, ind], idx) => {
      const color = OVERLAY_COLORS[idx % OVERLAY_COLORS.length]
      // Check if indicator has bullish/bearish coloring signals
      const bullish = ind.outputs['is_bullish']
      const bearish = ind.outputs['is_bearish']
      const hasDirectionColor = !!(bullish || bearish)

      for (const [outputName, values] of Object.entries(ind.outputs)) {
        if (META_OUTPUTS.has(outputName)) continue
        const lineData: (LineData<Time> & { color?: string })[] = []
        for (let i = 0; i < values.length; i++) {
          if (values[i] != null) {
            const point: LineData<Time> & { color?: string } = {
              time: bars[i].time as Time,
              value: values[i]!,
            }
            // Apply red/green coloring from is_bullish/is_bearish signals
            if (hasDirectionColor) {
              if (bullish?.[i] === 1) point.color = '#22c55e'
              else if (bearish?.[i] === 1) point.color = '#ef4444'
            }
            lineData.push(point)
          }
        }
        if (lineData.length === 0) continue
        const lineSeries = mainChart.addSeries(LineSeries, {
          color: hasDirectionColor ? '#22c55e' : color,
          lineWidth: hasDirectionColor ? 2 : 1,
          title: `${ind.name} ${outputName !== 'value' ? outputName : ''}`.trim(),
          priceLineVisible: false,
          lastValueVisible: false,
        })
        lineSeries.setData(lineData)
      }
    })

    // SMC / indicator markers (HH, HL, LH, LL, iH, iL, BOS, CHoCH)
    const allMarkers: { time: Time; position: 'aboveBar' | 'belowBar'; color: string; shape: 'circle' | 'arrowUp' | 'arrowDown'; text: string; size: number }[] = []
    for (const [_key, ind] of Object.entries(indicators)) {
      if (ind.markers && ind.markers.length > 0) {
        for (const m of ind.markers) {
          if (m.bar >= 0 && m.bar < bars.length) {
            const isBos = m.label === 'BOS' || m.label === 'CHoCH'
            allMarkers.push({
              time: bars[m.bar].time as Time,
              position: m.position,
              color: m.color,
              shape: isBos ? 'circle' : (m.position === 'aboveBar' ? 'arrowDown' : 'arrowUp'),
              text: m.label,
              size: isBos ? 1 : (m.label.startsWith('i') ? 0.5 : 1),
            })
          }
        }
      }
    }
    if (allMarkers.length > 0) {
      // Sort by time (required by lightweight-charts)
      allMarkers.sort((a, b) => (a.time as number) - (b.time as number))
      createSeriesMarkers(candleSeries, allMarkers)
    }

    mainChart.timeScale().fitContent()

    // Oscillator sub-panes
    const subCharts: IChartApi[] = []
    const syncing = { current: false }

    oscillators.forEach(([_key, ind], idx) => {
      const subWrapper = document.createElement('div')
      subWrapper.style.height = `${oscHeight}px`
      subWrapper.style.borderTop = `1px solid ${gridColor}`
      container.appendChild(subWrapper)

      const subChart = createChart(subWrapper, {
        width: container.clientWidth,
        height: oscHeight,
        layout: { background: { type: ColorType.Solid, color: bg }, textColor },
        grid: {
          vertLines: { color: gridColor },
          horzLines: { color: gridColor },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: true, secondsVisible: false },
      })

      const color = OSCILLATOR_COLORS[idx % OSCILLATOR_COLORS.length]
      for (const [outputName, values] of Object.entries(ind.outputs)) {
        const lineData: LineData<Time>[] = []
        for (let i = 0; i < values.length; i++) {
          if (values[i] != null) {
            lineData.push({ time: bars[i].time as Time, value: values[i]! })
          }
        }
        if (lineData.length === 0) continue

        if (outputName === 'histogram') {
          const histSeries = subChart.addSeries(HistogramSeries, {
            color,
            title: `${ind.name} ${outputName}`,
          })
          const histData: HistogramData<Time>[] = lineData.map((d) => ({
            ...d,
            color: d.value >= 0 ? '#22c55e' : '#ef4444',
          }))
          histSeries.setData(histData)
        } else {
          const lineSeries = subChart.addSeries(LineSeries, {
            color,
            lineWidth: 1,
            title: `${ind.name} ${outputName !== 'value' ? outputName : ''}`.trim(),
            priceLineVisible: false,
            lastValueVisible: false,
          })
          lineSeries.setData(lineData)
        }
      }

      subChart.timeScale().fitContent()
      subCharts.push(subChart)

      // Sync time scales
      subChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing.current || !range) return
        syncing.current = true
        mainChart.timeScale().setVisibleLogicalRange(range)
        subCharts.forEach((sc) => {
          if (sc !== subChart) sc.timeScale().setVisibleLogicalRange(range)
        })
        syncing.current = false
      })
    })

    // Sync main chart to sub-charts
    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (syncing.current || !range) return
      syncing.current = true
      subCharts.forEach((sc) => sc.timeScale().setVisibleLogicalRange(range))
      syncing.current = false
    })

    subChartsRef.current = subCharts

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return
      const w = containerRef.current.clientWidth
      const oscCount = subCharts.length
      const mh = containerRef.current.clientHeight - oscCount * oscHeight
      mainChart.applyOptions({ width: w, height: Math.max(mh, 200) })
      subCharts.forEach((sc) => sc.applyOptions({ width: w, height: oscHeight }))
    })
    ro.observe(container)

    return () => {
      ro.disconnect()
      cleanup()
    }
  }, [bars, indicators, dark])

  function cleanup() {
    mainChartRef.current?.remove()
    mainChartRef.current = null
    subChartsRef.current.forEach((sc) => sc.remove())
    subChartsRef.current = []
    if (containerRef.current) {
      containerRef.current.innerHTML = ''
    }
  }

  if (bars.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-content-muted text-sm">
        No data to display. Load bars from MT5 or upload a CSV.
      </div>
    )
  }

  return <div ref={containerRef} className="w-full h-full" />
}
