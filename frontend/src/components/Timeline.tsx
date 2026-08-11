import type { ItineraryPlan } from '../lib/types'

interface TimelineProps {
  itinerary: ItineraryPlan | null
}

export default function Timeline({ itinerary }: TimelineProps) {
  if (!itinerary) {
    return (
      <div className="flex flex-1 items-center justify-center bg-white">
        <div className="text-center text-gray-300">
          <p className="text-4xl mb-3">🗺️</p>
          <p className="text-sm">行程计划生成后会显示在这里</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-white">
      <div className="max-w-2xl mx-auto p-6">
        {/* 标题卡片 */}
        <div className="rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 p-6 text-white mb-6">
          <h1 className="text-2xl font-bold mb-1">{itinerary.title}</h1>
          <p className="text-emerald-100 text-sm">
            {itinerary.requirements.destination} · {itinerary.days.length} 天 · 预估总花费 ¥
            {itinerary.total_budget}
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            {itinerary.requirements.pace && (
              <span className="rounded-full bg-white/20 px-3 py-1">节奏：{itinerary.requirements.pace}</span>
            )}
            {itinerary.requirements.travelers && (
              <span className="rounded-full bg-white/20 px-3 py-1">人数：{itinerary.requirements.travelers}</span>
            )}
            {itinerary.requirements.budget && (
              <span className="rounded-full bg-white/20 px-3 py-1">预算：¥{itinerary.requirements.budget}</span>
            )}
            {itinerary.requirements.preferences && (
              <span className="rounded-full bg-white/20 px-3 py-1">偏好：{itinerary.requirements.preferences}</span>
            )}
          </div>
        </div>

        {/* 逐日活动 */}
        <div className="relative space-y-6">
          {itinerary.days.map((day, dayIdx) => (
            <div key={day.day} className="relative pl-10">
              {/* 时间线竖线 */}
              {dayIdx < itinerary.days.length - 1 && (
                <div className="absolute left-4 top-8 bottom-[-24px] w-px bg-emerald-200" />
              )}
              {/* 时间点圆点 */}
              <div className="absolute left-0 top-1 flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-semibold text-sm">
                {day.day}
              </div>

              <div className="rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-semibold text-gray-800">第 {day.day} 天</h2>
                  <span className="text-sm text-emerald-600 font-medium">¥{day.day_cost}</span>
                </div>
                {day.summary && <p className="text-sm text-gray-500 mb-3">{day.summary}</p>}

                <div className="space-y-3">
                  {day.activities.map((act, i) => (
                    <div key={i} className="flex gap-3">
                      <div className="w-20 shrink-0 pt-0.5 text-xs font-medium text-gray-400">{act.time}</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-gray-800">{act.title}</span>
                          {act.cost > 0 && <span className="text-xs text-gray-400">¥{act.cost}</span>}
                        </div>
                        {act.location && <div className="text-xs text-gray-500">📍 {act.location}</div>}
                        {act.detail && <div className="text-xs text-gray-400 mt-0.5">{act.detail}</div>}
                        {act.transport && (
                          <div className="mt-1 inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                            🚗 {act.transport}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
