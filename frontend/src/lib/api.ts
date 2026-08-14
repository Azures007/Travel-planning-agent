import type { ItineraryPlan, SessionInfo } from './types'

const BASE = '/api'

async function jsonRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json() as Promise<T>
}

export async function createSession(): Promise<SessionInfo> {
  return jsonRequest<SessionInfo>(`${BASE}/sessions`, { method: 'POST' })
}

export async function listSessions(): Promise<SessionInfo[]> {
  return jsonRequest<SessionInfo[]>(`${BASE}/sessions`)
}

export async function deleteSession(sessionId: number): Promise<void> {
  await jsonRequest<void>(`${BASE}/sessions/${sessionId}`, { method: 'DELETE' })
}

export interface SessionDetail {
  id: number
  title: string
  pending_question: string | null
  messages: {
    id: number
    role: 'user' | 'assistant'
    content: string
    tool_calls?: unknown[]
  }[]
  itinerary: ItineraryPlan | null
}

export async function getSession(sessionId: number): Promise<SessionDetail> {
  return jsonRequest<SessionDetail>(`${BASE}/sessions/${sessionId}`)
}

export type SSEEvent =
  | { type: 'agent_message'; data: { text: string } }
  | { type: 'tool_result'; data: { name: string; result: unknown } }
  | { type: 'itinerary'; data: { plan: ItineraryPlan } }
  | { type: 'question'; data: { question: string; waiting: boolean } }
  | {
      type: 'validation_report'
      data: { warnings: { rule: string; level: string; message: string }[] }
    }
  | { type: 'error'; data: { message: string } }
  | { type: 'done'; data: Record<string, never> }

/** 发送用户消息并通过 SSE 流式接收 agent 事件 */
export async function sendChatMessage(
  sessionId: number,
  content: string,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, content }),
  })
  if (!res.ok || !res.body) {
    throw new Error(`聊天请求失败: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 以空行分隔事件
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data: ')) continue
      try {
        const event = JSON.parse(line.slice(6)) as SSEEvent
        onEvent(event)
      } catch {
        // 忽略无法解析的分片
      }
    }
  }
}
