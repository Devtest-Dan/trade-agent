type MessageHandler = (data: any) => void

class WSClient {
  private ws: WebSocket | null = null
  private handlers: Map<string, MessageHandler[]> = new Map()
  private reconnectTimer: number | null = null
  private _connected = false

  get connected() { return this._connected }

  connect(token: string) {
    if (this.ws?.readyState === WebSocket.OPEN) return

    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    let wsUrl: string
    if (isLocalhost) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      wsUrl = `${protocol}//${window.location.host}/ws?token=${token}`
    } else {
      const ngrokHost = 'decoctive-semipalmate-brian.ngrok-free.dev'
      wsUrl = `wss://${ngrokHost}/ws?token=${token}`
    }
    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      this._connected = true
      this.emit('connection', { connected: true })

      // Heartbeat
      setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send('ping')
        }
      }, 30000)
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type) {
          this.emit(data.type, data)
        }
      } catch { /* ignore non-JSON */ }
    }

    this.ws.onclose = () => {
      this._connected = false
      this.emit('connection', { connected: false })
      // Auto-reconnect after 3s
      this.reconnectTimer = window.setTimeout(() => {
        this.connect(token)
      }, 3000)
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this._connected = false
  }

  on(type: string, handler: MessageHandler) {
    const existing = this.handlers.get(type) || []
    existing.push(handler)
    this.handlers.set(type, existing)
  }

  off(type: string, handler: MessageHandler) {
    const existing = this.handlers.get(type) || []
    this.handlers.set(type, existing.filter(h => h !== handler))
  }

  private emit(type: string, data: any) {
    const handlers = this.handlers.get(type) || []
    handlers.forEach(h => h(data))
  }
}

export const wsClient = new WSClient()
