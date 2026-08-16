import { useState } from 'react'
import type { ItineraryPlan } from '../lib/types'
import { useToast } from './ToastProvider'

interface TimelineProps {
  itinerary: ItineraryPlan | null
  sessionId: number | null
  onItineraryUpdate?: (itinerary: ItineraryPlan) => void
  onSendMessage?: (message: string) => void
}

export default function Timeline({ itinerary, sessionId, onItineraryUpdate, onSendMessage }: TimelineProps) {
  const toast = useToast()
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [editingActivity, setEditingActivity] = useState<{dayIdx: number, actIdx: number} | null>(null)
  const [editForm, setEditForm] = useState<any>({})
  const [showCompareModal, setShowCompareModal] = useState(false)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [selectedAlternative, setSelectedAlternative] = useState<any>(null)
  const [alternatives, setAlternatives] = useState<any[]>([])

  const handleExportHTML = () => {
    if (!sessionId) return
    window.open(`http://localhost:8000/api/export/${sessionId}/html`, '_blank')
    setShowExportMenu(false)
  }

  const handleShare = async () => {
    if (!sessionId) return
    try {
      const response = await fetch(`http://localhost:8000/api/export/${sessionId}/share`)
      const data = await response.json()

      // 复制到剪贴板
      await navigator.clipboard.writeText(data.url)
      toast.success('分享链接已复制到剪贴板！')
    } catch (error) {
      toast.error('生成分享链接失败，请重试')
    }
    setShowExportMenu(false)
  }

  const handlePrint = () => {
    if (!sessionId) return
    const printWindow = window.open(`http://localhost:8000/api/export/${sessionId}/html`, '_blank')
    if (printWindow) {
      printWindow.onload = () => {
        printWindow.print()
      }
    }
    setShowExportMenu(false)
  }

  const handleViewMap = () => {
    if (!sessionId) return
    window.open(`/map.html?session_id=${sessionId}`, '_blank')
    setShowExportMenu(false)
  }

  const startEdit = (dayIdx: number, actIdx: number, activity: any) => {
    setEditingActivity({ dayIdx, actIdx })
    setEditForm({ ...activity })
  }

  const cancelEdit = () => {
    setEditingActivity(null)
    setEditForm({})
  }

  const saveEdit = async () => {
    if (!editingActivity || !sessionId) return

    try {
      const response = await fetch(
        `http://localhost:8000/api/edit/${sessionId}/day/${editingActivity.dayIdx}/activity/${editingActivity.actIdx}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(editForm)
        }
      )

      if (!response.ok) throw new Error('更新失败')

      const data = await response.json()
      onItineraryUpdate?.(data.itinerary)
      setEditingActivity(null)
      setEditForm({})
      toast.success('活动已更新')
    } catch (error) {
      toast.error('保存失败，请重试')
    }
  }

  const deleteActivity = async (dayIdx: number, actIdx: number) => {
    if (!sessionId) return
    if (!confirm('确定要删除这个活动吗？')) return

    try {
      const response = await fetch(
        `http://localhost:8000/api/edit/${sessionId}/day/${dayIdx}/activity/${actIdx}`,
        { method: 'DELETE' }
      )

      if (!response.ok) throw new Error('删除失败')

      const data = await response.json()
      onItineraryUpdate?.(data.itinerary)
      toast.success('活动已删除')
    } catch (error) {
      toast.error('删除失败，请重试')
    }
  }

  const generateAlternatives = async () => {
    if (!sessionId) return

    try {
      const response = await fetch('http://localhost:8000/api/compare/generate-alternatives', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      })

      if (!response.ok) throw new Error('生成失败')

      const data = await response.json()
      setAlternatives(data.alternatives)
      setShowCompareModal(true)
    } catch (error) {
      toast.error('生成备选方案失败，请重试')
    }
  }
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
          <div className="flex items-start justify-between mb-1">
            <div className="flex-1">
              <h1 className="text-2xl font-bold mb-1">{itinerary.title}</h1>
              <p className="text-emerald-100 text-sm">
                {itinerary.requirements.destination} · {itinerary.days.length} 天 · 预估总花费 ¥
                {itinerary.total_budget}
              </p>
            </div>
            {/* 操作按钮 */}
            <div className="flex gap-2 ml-4">
              {/* 方案对比按钮 */}
              <button
                onClick={generateAlternatives}
                className="rounded-lg bg-white/20 hover:bg-white/30 px-4 py-2 text-sm font-medium transition-colors whitespace-nowrap"
              >
                🔄 其他方案
              </button>
              {/* 导出按钮 */}
              <div className="relative">
                <button
                  onClick={() => setShowExportMenu(!showExportMenu)}
                  className="rounded-lg bg-white/20 hover:bg-white/30 px-4 py-2 text-sm font-medium transition-colors whitespace-nowrap"
                >
                  📤 导出
                </button>
                {showExportMenu && (
                  <>
                    <div
                      className="fixed inset-0 z-10"
                      onClick={() => setShowExportMenu(false)}
                    />
                    <div className="absolute right-0 mt-2 w-48 rounded-lg bg-white shadow-lg py-2 z-20">
                      <button
                        onClick={handleViewMap}
                        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                      >
                        🗺️ 查看地图
                      </button>
                      <button
                        onClick={handleExportHTML}
                        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                      >
                        🌐 在新窗口打开
                      </button>
                      <button
                        onClick={handlePrint}
                        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                      >
                        🖨️ 打印/保存PDF
                      </button>
                      <button
                        onClick={handleShare}
                        className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                      >
                        🔗 复制分享链接
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
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
            {itinerary.requirements.departure_date && (
              <span className="rounded-full bg-white/20 px-3 py-1">出发：{itinerary.requirements.departure_date}</span>
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
                  {day.activities.map((act, actIdx) => {
                    const isEditing = editingActivity?.dayIdx === dayIdx && editingActivity?.actIdx === actIdx

                    if (isEditing) {
                      // 编辑模式
                      return (
                        <div key={actIdx} className="border border-blue-500 rounded-lg p-3 bg-blue-50">
                          <div className="space-y-2 text-sm">
                            <input
                              className="w-full px-2 py-1 border rounded text-sm"
                              placeholder="时间"
                              value={editForm.time || ''}
                              onChange={(e) => setEditForm({ ...editForm, time: e.target.value })}
                            />
                            <input
                              className="w-full px-2 py-1 border rounded text-sm"
                              placeholder="标题"
                              value={editForm.title || ''}
                              onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                            />
                            <input
                              className="w-full px-2 py-1 border rounded text-sm"
                              placeholder="地点"
                              value={editForm.location || ''}
                              onChange={(e) => setEditForm({ ...editForm, location: e.target.value })}
                            />
                            <textarea
                              className="w-full px-2 py-1 border rounded text-sm"
                              placeholder="详情"
                              rows={2}
                              value={editForm.detail || ''}
                              onChange={(e) => setEditForm({ ...editForm, detail: e.target.value })}
                            />
                            <input
                              className="w-full px-2 py-1 border rounded text-sm"
                              placeholder="费用"
                              type="number"
                              value={editForm.cost || 0}
                              onChange={(e) => setEditForm({ ...editForm, cost: parseFloat(e.target.value) || 0 })}
                            />
                            <div className="flex gap-2 pt-2">
                              <button
                                onClick={saveEdit}
                                className="px-3 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700"
                              >
                                保存
                              </button>
                              <button
                                onClick={cancelEdit}
                                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-xs hover:bg-gray-300"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        </div>
                      )
                    }

                    // 正常显示模式
                    return (
                      <div key={actIdx} className="flex gap-3 group relative">
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
                        {/* 编辑/删除按钮 */}
                        <div className="absolute -right-2 top-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                          <button
                            onClick={() => startEdit(dayIdx, actIdx, act)}
                            className="p-1 rounded bg-white border border-gray-300 hover:bg-gray-50 text-xs"
                            title="编辑"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => deleteActivity(dayIdx, actIdx)}
                            className="p-1 rounded bg-white border border-gray-300 hover:bg-red-50 text-xs"
                            title="删除"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 方案对比弹窗 */}
      {showCompareModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-800">选择备选方案</h2>
                <p className="text-sm text-gray-500 mt-1">选择一个方案后，系统将基于新预算重新生成行程</p>
              </div>
              <button
                onClick={() => setShowCompareModal(false)}
                className="text-gray-400 hover:text-gray-600 text-2xl"
              >
                ×
              </button>
            </div>
            <div className="p-6 space-y-4">
              {alternatives.map((alt, idx) => (
                <div
                  key={idx}
                  className="border-2 border-gray-200 rounded-lg p-4 hover:border-emerald-500 hover:shadow-md transition-all cursor-pointer group"
                  onClick={() => {
                    setSelectedAlternative(alt)
                    setShowConfirmModal(true)
                  }}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-800 group-hover:text-emerald-600 transition-colors">
                        {alt.style}
                      </h3>
                      <p className="text-sm text-gray-500">{alt.description}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-bold text-emerald-600">¥{alt.budget}</div>
                      <div className="text-xs text-gray-400">
                        {alt.budget > (itinerary.total_budget || 0) ? '↑' : '↓'}
                        {Math.abs(((alt.budget / (itinerary.total_budget || 1)) - 1) * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-gray-600 border-t border-gray-100 pt-2 mt-2">
                    💡 基于当前行程，调整预算和品质等级后重新生成
                  </div>
                </div>
              ))}
            </div>
            <div className="sticky bottom-0 bg-gradient-to-r from-emerald-50 to-teal-50 px-6 py-4 border-t border-emerald-100">
              <div className="flex items-start gap-3">
                <span className="text-2xl">⚠️</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-700 mb-1">重要提示</p>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    选择方案后，系统将基于新的预算重新规划整个行程。当前行程将被覆盖，建议您先使用"导出"功能保存当前行程。
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 确认对话框 */}
      {showConfirmModal && selectedAlternative && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
          <div className="bg-white rounded-xl max-w-md w-full shadow-2xl">
            <div className="bg-gradient-to-r from-emerald-500 to-teal-600 text-white px-6 py-4 rounded-t-xl">
              <h3 className="text-xl font-bold">确认选择方案</h3>
            </div>
            <div className="p-6">
              <div className="mb-4">
                <div className="text-lg font-semibold text-gray-800 mb-2">
                  {selectedAlternative.style}
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">新预算：</span>
                    <span className="font-semibold text-emerald-600">¥{selectedAlternative.budget}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">说明：</span>
                    <span className="text-gray-800">{selectedAlternative.description}</span>
                  </div>
                </div>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
                <div className="flex items-start gap-2">
                  <span className="text-amber-600 text-xl">⚠️</span>
                  <div className="flex-1 text-sm">
                    <p className="font-medium text-amber-800 mb-1">重要提示</p>
                    <p className="text-amber-700 leading-relaxed">
                      确认后，系统将基于新预算重新生成整个行程。<strong>当前行程将被覆盖</strong>，建议您先使用"导出"功能保存。
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <div className="text-sm">
                  <p className="font-medium text-blue-800 mb-2">💡 接下来会发生什么？</p>
                  <p className="text-blue-700 leading-relaxed">
                    点击"确认并重新生成"后，系统将自动开始重新规划行程，无需手动输入。整个过程大约需要 30-60 秒。
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setShowConfirmModal(false)
                    setSelectedAlternative(null)
                  }}
                  className="flex-1 px-4 py-2 border-2 border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    if (onSendMessage && selectedAlternative) {
                      const message = `根据${selectedAlternative.style}方案重新规划，预算${selectedAlternative.budget}元`
                      onSendMessage(message)
                    }
                    setShowConfirmModal(false)
                    setShowCompareModal(false)
                    setSelectedAlternative(null)
                  }}
                  className="flex-1 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-lg font-medium hover:from-emerald-600 hover:to-teal-700 transition-colors"
                >
                  确认并重新生成
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
