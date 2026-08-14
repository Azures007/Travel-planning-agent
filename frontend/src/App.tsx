import { useCallback, useEffect, useRef, useState } from 'react'
import ChatPanel from './components/ChatPanel'
import Timeline from './components/Timeline'
import SessionSidebar from './components/SessionSidebar'
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

      const assistantBuffer = { text: '' }
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      try {
        await sendChatMessage(sid, text, (event) => {
          if (event.type === 'agent_message') {
            assistantBuffer.text += event.data.text
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                role: 'assistant',
                content: assistantBuffer.text,
              }
              return next
            })
          } else if (event.type === 'itinerary') {
            setItinerary(event.data.plan)
          } else if (event.type === 'question') {
            setWaitingFor(event.data.question)
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
        await refreshSessions()
      }
    },
    [activeSession, refreshSessions, createSession],
  )

  return (
    <div className="flex h-screen bg-gray-50">
      <SessionSidebar
        sessions={sessions}
        activeId={activeSession}
        onNew={newSession}
        onSelect={openSession}
        onDelete={handleDelete}
        onRename={handleRename}
      />
      <div className="flex flex-1 min-w-0">
        <ChatPanel
          messages={messages}
          loading={loading}
          waitingFor={waitingFor}
          onSend={handleSend}
          disabled={false}
        />
        <Timeline itinerary={itinerary} />
      </div>
    </div>
  )
}
