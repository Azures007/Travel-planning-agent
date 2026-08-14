// 与后端 app/schemas.py 对应的类型定义

export interface Activity {
  time: string
  title: string
  location: string
  detail: string
  transport: string
  cost: number
}

export interface DayPlan {
  day: number
  date: string
  summary: string
  activities: Activity[]
  day_cost: number
}

export interface TripRequirements {
  destination: string
  days: number | null
  budget: number | null
  travelers: string
  pace: string
  preferences: string
  departure_date: string
  special_notes: string
}

export interface ItineraryPlan {
  title: string
  requirements: TripRequirements
  total_budget: number
  days: DayPlan[]
}

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant'
  content: string
  tool_calls?: unknown[]
}

export interface SessionInfo {
  id: number
  title: string
  created_at?: string
}
