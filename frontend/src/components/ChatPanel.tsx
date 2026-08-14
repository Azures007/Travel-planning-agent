import { useEffect, useRef, useState } from 'react'

interface ChatPanelProps {
  messages: { role: 'user' | 'assistant'; content: string }[]
  loading: boolean
  waitingFor?: string | null
  processText?: string
  onSend: (text: string) => void
  disabled: boolean
}

export default function ChatPanel({
  messages,
  loading,
  waitingFor = null,
  processText = '',
  onSend,
  disabled,
}: ChatPanelProps) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, waitingFor, processText])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    onSend(text)
    setInput('')
  }

  const isWaiting = waitingFor !== null && !loading
  const inputDisabled = disabled || loading

  return (
    <div className="flex w-[46%] min-w-[380px] flex-col border-r border-gray-200">
      {/* 等待回答横幅 */}
      {isWaiting && (
        <div className="mx-3 mt-3 rounded-xl bg-amber-50 border border-amber-200 px-4 py-2.5 text-sm text-amber-700">
          ⏳ 等你回答：{waitingFor}
        </div>
      )}

      {/* 收集阶段进度状态条（模型查工具时的短句，折叠展示） */}
      {loading && processText.trim() && (
        <div className="mx-3 mt-3 flex items-start gap-2 rounded-xl bg-gray-50 border border-gray-200 px-4 py-2.5 text-xs text-gray-500">
          <span className="shrink-0 mt-0.5">🔍</span>
          <span className="leading-relaxed line-clamp-2">{processText.trim()}</span>
        </div>
      )}

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="mt-16 text-center text-gray-400">
            <p className="text-xl mb-2">👋 旅行规划助手</p>
            <p className="text-sm">告诉我你想去哪里、玩几天、预算多少，我来帮你规划行程。</p>
            <p className="text-sm mt-1 text-gray-300">例如：「我想去大理玩4天，预算5000，两个人」</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-white border border-gray-200 rounded-bl-sm'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-gray-400">
              <span className="inline-flex gap-1">
                <span className="animate-bounce">●</span>
                <span className="animate-bounce" style={{ animationDelay: '0.15s' }}>●</span>
                <span className="animate-bounce" style={{ animationDelay: '0.3s' }}>●</span>
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <form onSubmit={handleSubmit} className="border-t border-gray-200 p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            rows={1}
            placeholder={
              inputDisabled
                ? disabled
                  ? '先新建一个会话'
                  : '思考中…'
                : isWaiting
                  ? '回答…'
                  : '输入你的旅行需求…'
            }
            disabled={inputDisabled}
            className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
          />
          <button
            type="submit"
            disabled={inputDisabled || !input.trim()}
            className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </form>
    </div>
  )
}
