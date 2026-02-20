import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, Check } from 'lucide-react'
import { api } from '../api/client'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  strategyId: number
  onApplyConfig: (config: any) => void
}

const CONFIG_TAG_RE = /<config_update>([\s\S]*?)<\/config_update>/g

function parseConfigUpdates(text: string): { cleanText: string; configs: any[] } {
  const configs: any[] = []
  const cleanText = text.replace(CONFIG_TAG_RE, (_, json) => {
    try {
      configs.push(JSON.parse(json.trim()))
    } catch {
      // If JSON parse fails, leave the text as-is
    }
    return ''
  }).trim()
  return { cleanText, configs }
}

export default function StrategyChat({ strategyId, onApplyConfig }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [appliedIndexes, setAppliedIndexes] = useState<Set<number>>(new Set())
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending) return

    const userMsg: Message = { role: 'user', content: text }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setSending(true)

    try {
      const { reply } = await api.chatWithStrategy(strategyId, newMessages)
      setMessages([...newMessages, { role: 'assistant', content: reply }])
    } catch (e: any) {
      setMessages([
        ...newMessages,
        { role: 'assistant', content: `Error: ${e.message}` },
      ])
    }
    setSending(false)
  }

  const handleApply = (config: any, msgIndex: number) => {
    onApplyConfig(config)
    setAppliedIndexes((prev) => new Set(prev).add(msgIndex))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-3 p-3 min-h-0">
        {messages.length === 0 && (
          <div className="text-center text-content-faint text-sm py-8">
            <p>Ask the AI about this strategy.</p>
            <p className="text-xs mt-1 text-content-faint">
              Try: "What does this strategy do?" or "Add an ATR filter"
            </p>
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.role === 'user') {
            return (
              <div key={i} className="flex justify-end">
                <div className="bg-brand-600/30 text-content rounded-lg px-3 py-2 max-w-[85%] text-sm whitespace-pre-wrap">
                  {msg.content}
                </div>
              </div>
            )
          }

          const { cleanText, configs } = parseConfigUpdates(msg.content)
          return (
            <div key={i} className="flex justify-start">
              <div className="bg-surface-raised text-content rounded-lg px-3 py-2 max-w-[85%] text-sm space-y-2">
                {cleanText && <div className="whitespace-pre-wrap">{cleanText}</div>}
                {configs.map((cfg, ci) => (
                  <div key={ci} className="border border-line rounded p-2 mt-2">
                    <details>
                      <summary className="text-xs text-content-muted cursor-pointer hover:text-content">
                        View suggested config
                      </summary>
                      <pre className="mt-1 text-[11px] text-content-secondary overflow-auto max-h-48 bg-surface-card p-2 rounded">
                        {JSON.stringify(cfg, null, 2)}
                      </pre>
                    </details>
                    <button
                      onClick={() => handleApply(cfg, i)}
                      disabled={appliedIndexes.has(i)}
                      className={`mt-2 flex items-center gap-1 px-3 py-1 text-xs rounded transition-colors ${
                        appliedIndexes.has(i)
                          ? 'bg-emerald-600/20 text-emerald-400 cursor-default'
                          : 'bg-brand-600 text-white hover:bg-brand-700'
                      }`}
                    >
                      {appliedIndexes.has(i) ? (
                        <>
                          <Check size={12} /> Applied
                        </>
                      ) : (
                        'Apply Changes'
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )
        })}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-surface-raised text-content-muted rounded-lg px-3 py-2 text-sm flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" /> Thinking...
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-line/30 p-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this strategy..."
            rows={1}
            className="flex-1 px-3 py-2 bg-surface-inset border border-line rounded-lg text-content text-sm placeholder-content-faint focus:outline-none focus:border-brand-500 resize-none"
          />
          <button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className="px-3 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
