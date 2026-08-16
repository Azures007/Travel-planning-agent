import { useCallback, useEffect, useRef, useState } from 'react'
import ChatPanel from './components/ChatPanel'
import Timeline from './components/Timeline'
import TimelineSkeleton from './components/TimelineSkeleton'
import SessionSidebar from './components/SessionSidebar'
import { ToastProvider } from './components/ToastProvider'
import { createSession, deleteSession, getSession, listSessions, renameSession, sendChatMessage } from './lib/api'
import type { ItineraryPlan, SessionInfo } from './lib/types'

export default function App() {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [activeSession, setActiveSession] = useState<number | null>(null)
  const [itinerary, setItinerary] = useState<ItineraryPlan | null>(null)
  const [messages, setMessages] = useState<
    { role: 'user' | 'assistant'; content: string }[]
  >([])
  const [loading, setLoading] = useState(false)
  const [waitingFor, setWaitingFor] = useState<string | null>(null)
  // collect 阶段的进度文本（模型查工具时的短句，折叠为状态条）
  const [processText, setProcessText] = useState('')
  const itineraryRef = useRef<ItineraryPlan | null>(null)
  // 刚自动新建的会话：跳过 getSession 加载，避免覆盖流式更新的消息
  const skipLoadRef = useRef<number | null>(null)

  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch {
      // 忽略列表加载失败
    }
  }, [])

  useEffect(() => {
    itineraryRef.current = itinerary
  }, [itinerary])

  const newSession = useCallback(async () => {
    try {
      const s = await createSession()
      await refreshSessions()
      setActiveSession(s.id)
      setMessages([])
      setItinerary(null)
      setWaitingFor(null)
    } catch (e) {
      console.error('创建会话失败', e)
    }
  }, [refreshSessions])

  const handleItineraryUpdate = useCallback((updatedItinerary: any) => {
    setItinerary(updatedItinerary)
  }, [])

  // 移动端标签页切换
  const [mobileTab, setMobileTab] = useState<'chat' | 'itinerary'>('chat')
  const [showSidebar, setShowSidebar] = useState(false)

  // 进入页面：不选中任何历史会话（显示空输入界面），用户第一次输入时自动新建
  useEffect(() => {
    void refreshSessions()
  }, [refreshSessions])

  useEffect(() => {
    if (activeSession === null) return
    // 自动新建的会话：跳过加载（消息正在流式更新，避免被覆盖）
    if (skipLoadRef.current === activeSession) {
      skipLoadRef.current = null
      return
    }
    void (async () => {
      try {
        const detail = await getSession(activeSession)
        setMessages(
          detail.messages.map((m) => ({ role: m.role, content: m.content })),
        )
        setItinerary(detail.itinerary)
        // 恢复中断等待状态
        setWaitingFor(detail.pending_question || null)
        setProcessText('')
      } catch (e) {
        console.error('加载会话失败', e)
      }
    })()
  }, [activeSession])

  const openSession = useCallback(async (id: number) => {
    setActiveSession(id)
  }, [])

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await deleteSession(id)
        await refreshSessions()
        // 若删的是当前会话，清空右侧
        setActiveSession((cur) => {
          if (cur === id) {
            setMessages([])
            setItinerary(null)
            setWaitingFor(null)
            return null
          }
          return cur
        })
      } catch (e) {
        console.error('删除会话失败', e)
      }
    },
    [refreshSessions],
  )

  const handleRename = useCallback(
    async (id: number, title: string) => {
      try {
        await renameSession(id, title)
        await refreshSessions()
      } catch (e) {
        console.error('重命名会话失败', e)
      }
    },
    [refreshSessions],
  )

  const handleReuse = useCallback(
    async (id: number) => {
      try {
        // 获取原会话的行程信息
        const response = await fetch(`http://localhost:8000/api/sessions/${id}`)
        const session = await response.json()

        if (!session.itinerary) {
          alert('该会话还没有生成行程')
          return
        }

        const requirements = session.itinerary.requirements

        // 创建新会话
        const newSession = await createSession()
        await refreshSessions()
        setActiveSession(newSession.id)
        skipLoadRef.current = newSession.id  // 跳过加载
        setMessages([])
        setItinerary(null)

        // 构造提示信息
        const prompt = `我想去${requirements.destination}玩${requirements.days || 3}天，预算${requirements.budget || 3000}元${requirements.travelers ? `，${requirements.travelers}` : ''}`

        // 使用与 handleSend 相同的逻辑发送消息
        const userMsg = { role: 'user' as const, content: prompt }
        setMessages([userMsg])
        setLoading(true)
        setWaitingFor(null)
        setProcessText('')

        // 调用 chat API
        const resp = await fetch('http://localhost:8000/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: newSession.id, content: prompt }),
        })

        if (!resp.ok) throw new Error('请求失败')

        const reader = resp.body?.getReader()
        if (!reader) throw new Error('无法读取响应流')

        const decoder = new TextDecoder()
        const assistantBuffer = { text: '' }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n\n')

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const json = line.slice(6)
            if (!json.trim()) continue

            const event = JSON.parse(json)

            if (event.type === 'process') {
              setProcessText(event.data.text || '')
            } else if (event.type === 'waiting_for') {
              setWaitingFor(event.data.tool || null)
            } else if (event.type === 'itinerary') {
              setItinerary(event.data)
            } else if (event.type === 'text') {
              assistantBuffer.text += event.data.text || ''
              setMessages((prev) => {
                const next = [...prev]
                if (next.length === 0 || next[next.length - 1].role !== 'assistant') {
                  next.push({ role: 'assistant', content: assistantBuffer.text })
                } else {
                  const lastMsg = next[next.length - 1]
                  if (lastMsg.content === assistantBuffer.text) return prev
                  next[next.length - 1] = { role: 'assistant', content: assistantBuffer.text }
                }
                return next
              })
            } else if (event.type === 'error') {
              assistantBuffer.text = event.data.message
              setMessages((prev) => {
                const next = [...prev]
                if (next[next.length - 1]?.role === 'assistant') {
                  next[next.length - 1] = { role: 'assistant', content: assistantBuffer.text }
                } else {
                  next.push({ role: 'assistant', content: assistantBuffer.text })
                }
                return next
              })
            } else if (event.type === 'done') {
              break
            }
          }
        }

        setLoading(false)
        setProcessText('')
        await refreshSessions()
      } catch (e) {
        console.error('复用行程失败', e)
        alert('复用失败，请重试')
        setLoading(false)
      }
    },
    [refreshSessions, createSession],
  )

  const handleSend = useCallback(
    async (text: string) => {
      // 无活动会话时，自动新建一个（用户第一次输入）
      let sid = activeSession
      if (sid === null) {
        const s = await createSession()
        skipLoadRef.current = s.id  // 跳过 getSession 加载，避免覆盖流式消息
        setActiveSession(s.id)
        sid = s.id
      }
      if (sid === null) return

      const userMsg = { role: 'user' as const, content: text }
      setMessages((prev) => [...prev, userMsg])
      setLoading(true)
      setWaitingFor(null)
      setProcessText('')

      const assistantBuffer = { text: '' }

      try {
        await sendChatMessage(sid, text, (event) => {
          if (event.type === 'process_message') {
            // collect 阶段的进度文本，累积为一行状态条
            setProcessText((prev) => prev + event.data.text)
          } else if (event.type === 'agent_message') {
            assistantBuffer.text += event.data.text
            setMessages((prev) => {
              const next = [...prev]
              // 如果最后一条不是 assistant 或没有消息，新建气泡
              if (next.length === 0 || next[next.length - 1].role !== 'assistant') {
                next.push({ role: 'assistant', content: assistantBuffer.text })
              } else {
                // 否则更新最后一条 assistant 消息
                // 去重：如果内容没变，不触发更新（避免 interrupt 恢复时的重复事件）
                const lastMsg = next[next.length - 1]
                if (lastMsg.content === assistantBuffer.text) {
                  return prev  // 内容未变，不更新
                }
                next[next.length - 1] = {
                  role: 'assistant',
                  content: assistantBuffer.text,
                }
              }
              return next
            })
          } else if (event.type === 'itinerary') {
            setItinerary(event.data.plan)
          } else if (event.type === 'question') {
            // question 事件：创建新的空 assistant 气泡，后续 agent_message 会填充
            // 去重：检查最近的 assistant 消息是否已经包含这个追问
            const questionText = event.data.question
            setMessages((prev) => {
              // 找到最近的 3 条 assistant 消息
              const recentAssistants = prev
                .filter(m => m.role === 'assistant')
                .slice(-3)

              // 如果最近的 assistant 消息中有任何一条内容等于这个追问，跳过
              const isDuplicate = recentAssistants.some(m => m.content === questionText)

              // 或者最后一条是空气泡，也跳过
              const lastMsg = prev[prev.length - 1]
              const isEmptyBubble = lastMsg?.role === 'assistant' && lastMsg.content === ''

              if (isDuplicate || isEmptyBubble) {
                return prev
              }

              // 创建新气泡
              return [...prev, { role: 'assistant', content: '' }]
            })
            // 重置 buffer
            assistantBuffer.text = ''
          } else if (event.type === 'error') {
            // 后端友好错误提示：填充到当前 assistant 气泡
            assistantBuffer.text = event.data.message
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                role: 'assistant',
                content: event.data.message,
              }
              return next
            })
          } else if (event.type === 'validation_report') {
            // 协议先行：校验警告暂只打日志，后续可渲染
            console.info('行程校验警告:', event.data.warnings)
          }
        })
      } catch (e) {
        const err = e as Error
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = {
            role: 'assistant',
            content: `请求失败：${err.message}`,
          }
          return next
        })
      } finally {
        setLoading(false)
        setProcessText('')
        await refreshSessions()
      }
    },
    [activeSession, refreshSessions, createSession],
  )

  return (
    <ToastProvider>
      <div className="flex h-screen bg-gray-50">
      {/* 侧边栏：桌面端始终显示，移动端通过按钮切换 */}
      <div className={`${showSidebar ? 'fixed inset-0 z-50 md:relative' : 'hidden md:block'}`}>
        {showSidebar && (
          <div className="absolute inset-0 bg-black/50 md:hidden" onClick={() => setShowSidebar(false)} />
        )}
        <div className={`${showSidebar ? 'relative' : ''} h-full`}>
          <SessionSidebar
            sessions={sessions}
            activeId={activeSession}
            onNew={newSession}
            onSelect={(id) => {
              openSession(id)
              setShowSidebar(false)
            }}
            onDelete={handleDelete}
            onRename={handleRename}
            onReuse={handleReuse}
          />
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex flex-1 min-w-0 flex-col md:flex-row">
        {/* 移动端顶部导航 */}
        <div className="flex md:hidden bg-white border-b border-gray-200">
          <button
            onClick={() => setShowSidebar(true)}
            className="px-4 py-3 text-gray-600 hover:bg-gray-50"
          >
            📋 会话
          </button>
          <button
            onClick={() => setMobileTab('chat')}
            className={`flex-1 py-3 text-sm font-medium ${
              mobileTab === 'chat' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-600'
            }`}
          >
            💬 对话
          </button>
          <button
            onClick={() => setMobileTab('itinerary')}
            className={`flex-1 py-3 text-sm font-medium ${
              mobileTab === 'itinerary' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-600'
            }`}
          >
            🗺️ 行程
          </button>
        </div>

        {/* 对话面板：桌面端始终显示，移动端根据tab显示 */}
        <div className={`${mobileTab === 'chat' ? 'flex' : 'hidden'} md:flex flex-1 min-w-0`}>
          <ChatPanel
            messages={messages}
            loading={loading}
            waitingFor={waitingFor}
            processText={processText}
            onSend={handleSend}
            disabled={false}
          />
        </div>

        {/* 行程面板：桌面端始终显示，移动端根据tab显示 */}
        <div className={`${mobileTab === 'itinerary' ? 'flex' : 'hidden'} md:flex flex-1 min-w-0`}>
          {loading && !itinerary ? (
            <TimelineSkeleton />
          ) : (
            <Timeline itinerary={itinerary} sessionId={activeSession} onItineraryUpdate={handleItineraryUpdate} onSendMessage={handleSend} />
          )}
        </div>
      </div>
    </div>
    </ToastProvider>
  )
}
