export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(' ')
}

export function formatPrice(price: number, decimals = 2): string {
  return price.toFixed(decimals)
}

export function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function directionColor(direction: string): string {
  if (direction.includes('LONG') || direction === 'BUY') return 'text-emerald-400'
  if (direction.includes('SHORT') || direction === 'SELL') return 'text-red-400'
  return 'text-content-muted'
}

export function statusColor(status: string): string {
  switch (status) {
    case 'pending': return 'bg-yellow-500/20 text-yellow-400'
    case 'approved':
    case 'executed': return 'bg-emerald-500/20 text-emerald-400'
    case 'rejected': return 'bg-red-500/20 text-red-400'
    case 'expired': return 'bg-content-muted/10 text-content-muted'
    default: return 'bg-content-muted/10 text-content-muted'
  }
}
