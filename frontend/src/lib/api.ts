import type { ItineraryPlan, SessionInfo } from './types'

const BASE = '/api'

/** API 错误类，携带状态码和详细信息 */
export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** 将 HTTP 状态码转换为用户友好的中文提示 */
function friendlyMessage(status: number, detail?: string): string {
  if (detail) return detail
  switch (status) {
    case 400:
      return '请求参数有误'
    case 401:
      return '未授权，请重新登录'
    case 403:
      return '没有权限执行此操作'
    case 404:
      return '请求的资源不存在'
    case 429:
      return '请求过于频繁，请稍后再试'
    case 500:
      return '服务器内部错误，请稍后重试'
    case 502:
    case 503:
    case 504:
      return '服务暂时不可用，请稍后重试'
    default:
      return `请求失败 (${status})`
  }
}

/** 带自动重试的 JSON 请求。
 *
 * - 对 5xx 错误和网络错误自动重试（默认 2 次，指数退避）
 * - 4xx 错误不重试（客户端错误，重试无意义）
 * - 抛出 ApiError，携带友好的中文提示
 */
async function jsonRequest<T>(
  url: string,
  options?: RequestInit,
  retries = 2,
): Promise<T> {
  let lastError: Error | null = null

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, options)

      if (res.ok) {
        // 204 No Content 或空响应体
        const text = await res.text()
        return (text ? JSON.parse(text) : undefined) as T
      }

      // 尝试解析后端返回的错误详情
      let detail: string | undefined
      try {
        const body = await res.json()
        detail = body?.detail || body?.message
      } catch {
        // 响应体不是 JSON，忽略
      }

      // 4xx 客户端错误：不重试，直接抛出
      if (res.status >= 400 && res.status < 500) {
        throw new ApiError(res.status, friendlyMessage(res.status, detail), detail)
      }

      // 5xx 服务端错误：记录后重试
      lastError = new ApiError(
        res.status,
        friendlyMessage(res.status, detail),
        detail,
      )
    } catch (err) {
      // ApiError（4xx）直接抛出，不重试
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
        throw err
      }
      // 网络错误或 5xx：记录，准备重试
      lastError = err instanceof Error ? err : new Error(String(err))
    }

    // 还有重试机会：指数退避后重试
    if (attempt < retries) {
      await new Promise((r) => setTimeout(r, 500 * Math.pow(2, attempt)))
    }
  }

  throw lastError ?? new Error('请求失败')
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

export async function renameSession(sessionId: number, title: string): Promise<SessionInfo> {
  return jsonRequest<SessionInfo>(`${BASE}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
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
  | { type: 'process_message'; data: { text: string } }
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
