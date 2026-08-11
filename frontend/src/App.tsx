import { useCallback, useEffect, useRef, useState } from 'react'
import ChatPanel from './components/ChatPanel'
import Timeline from './components/Timeline'
import SessionSidebar from './components/SessionSidebar'
import { createSession, getSession, listSessions, sendChatMessage } from './lib/api'
import type { ItineraryPlan, SessionInfo } from './lib/types'

export default function App() {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [activeSession, setActiveSession] = useState<number | null>(null)
  const [itinerary, setItinerary] = useState<ItineraryPlan | null>(null)
  const [messages, setMessages] = useState<
    { role: 'user' | 'assistant'; content: string }[]
  >([])
  const [loading, setLoading] = useState(false)
  const itineraryRef = useRef<ItineraryPlan | null>(null)

  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch {
      // 忽略列表加载失败
    }
  }, [])

  useEffect(() => {
    void refreshSessions()
  }, [refreshSessions])

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
    } catch (e) {
      console.error('创建会话失败', e)
    }
  }, [refreshSessions])

  useEffect(() => {
    if (activeSession === null) return
    void (async () => {
      try {
        const detail = await getSession(activeSession)
        setMessages(
          detail.messages.map((m) => ({ role: m.role, content: m.content })),
        )
        setItinerary(detail.itinerary)
      } catch (e) {
        console.error('加载会话失败', e)
      }
    })()
  }, [activeSession])

  const openSession = useCallback(async (id: number) => {
    setActiveSession(id)
  }, [])

  const handleSend = useCallback(
    async (text: string) => {
      if (!activeSession) return
      const userMsg = { role: 'user' as const, content: text }
      setMessages((prev) => [...prev, userMsg])
      setLoading(true)

      const assistantBuffer = { text: '' }
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      try {
        await sendChatMessage(activeSession, text, (event) => {
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
    [activeSession, refreshSessions],
  )

  return (
    <div className="flex h-screen bg-gray-50">
      <SessionSidebar
        sessions={sessions}
        activeId={activeSession}
        onNew={newSession}
        onSelect={openSession}
      />
      <div className="flex flex-1 min-w-0">
        <ChatPanel
          messages={messages}
          loading={loading}
          onSend={handleSend}
          disabled={activeSession === null}
        />
        <Timeline itinerary={itinerary} />
      </div>
    </div>
  )
}
