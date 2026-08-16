import { useState } from 'react'
import type { SessionInfo } from '../lib/types'

interface SessionSidebarProps {
  sessions: SessionInfo[]
  activeId: number | null
  onNew: () => void
  onSelect: (id: number) => void
  onDelete: (id: number) => void
  onRename: (id: number, title: string) => void
  onReuse?: (id: number) => void
}

export default function SessionSidebar({ sessions, activeId, onNew, onSelect, onDelete, onRename, onReuse }: SessionSidebarProps) {
  // 待确认删除的会话（null = 未弹出弹窗）
  const [pendingDelete, setPendingDelete] = useState<SessionInfo | null>(null)
  // 正在重命名的会话 id + 输入值
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')
  // 批量选择模式
  const [batchMode, setBatchMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  // 搜索关键词
  const [searchQuery, setSearchQuery] = useState('')

  const startRename = (s: SessionInfo) => {
    setEditingId(s.id)
    setEditValue(s.title)
  }

  const submitRename = (id: number) => {
    const title = editValue.trim()
    if (title) onRename(id, title)
    setEditingId(null)
  }

  const confirmDelete = () => {
    if (pendingDelete) onDelete(pendingDelete.id)
    setPendingDelete(null)
  }

  const toggleBatchMode = () => {
    setBatchMode(!batchMode)
    setSelectedIds(new Set())
  }

  const toggleSelect = (id: number) => {
    const next = new Set(selectedIds)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    setSelectedIds(next)
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === sessions.length) {
      // 当前全选，点击后取消全选
      setSelectedIds(new Set())
    } else {
      // 未全选，点击后全选
      setSelectedIds(new Set(sessions.map(s => s.id)))
    }
  }

  const confirmBatchDelete = () => {
    if (selectedIds.size === 0) return
    selectedIds.forEach(id => onDelete(id))
    setBatchMode(false)
    setSelectedIds(new Set())
  }

  // 搜索过滤
  const filteredSessions = sessions.filter(s =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="flex w-60 flex-col border-r border-gray-200 bg-white">
      <div className="p-3 space-y-2">
        <button
          onClick={onNew}
          className="w-full rounded-xl bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          ＋ 新建行程
        </button>
        {sessions.length > 0 && (
          <button
            onClick={toggleBatchMode}
            className={`w-full rounded-xl py-2 text-sm font-medium transition-colors ${
              batchMode
                ? 'bg-gray-600 text-white hover:bg-gray-700'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {batchMode ? '取消管理' : '管理'}
          </button>
        )}
        {batchMode && sessions.length > 0 && (
          <button
            onClick={toggleSelectAll}
            className="w-full rounded-xl py-2 text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
          >
            {selectedIds.size === sessions.length ? '取消全选' : '全选'}
          </button>
        )}
        {/* 搜索框 */}
        {sessions.length > 0 && (
          <div className="relative">
            <input
              type="text"
              placeholder="🔍 搜索行程..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl py-2 px-3 text-sm border border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                ×
              </button>
            )}
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-gray-400">暂无历史会话</p>
        )}
        {sessions.length > 0 && filteredSessions.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-gray-400">未找到匹配的行程</p>
        )}
        {filteredSessions.map((s) => (
          <div
            key={s.id}
            className={`group mb-1 flex items-center rounded-lg transition-colors ${
              activeId === s.id ? 'bg-blue-50' : 'hover:bg-gray-50'
            }`}
          >
            {/* 批量模式复选框 */}
            {batchMode && (
              <div className="pl-3">
                <input
                  type="checkbox"
                  checked={selectedIds.has(s.id)}
                  onChange={() => toggleSelect(s.id)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
              </div>
            )}

            {editingId === s.id ? (
              <input
                autoFocus
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={() => submitRename(s.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') submitRename(s.id)
                  if (e.key === 'Escape') setEditingId(null)
                }}
                className="mx-2 my-2 w-full rounded border border-blue-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            ) : (
              <button
                onClick={() => batchMode ? toggleSelect(s.id) : onSelect(s.id)}
                onDoubleClick={() => !batchMode && startRename(s)}
                className={`flex-1 truncate px-3 py-2.5 text-left text-sm ${
                  activeId === s.id ? 'text-blue-700' : 'text-gray-700'
                }`}
              >
                <div className="truncate font-medium">{s.title}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '会话'}
                </div>
              </button>
            )}
            {!batchMode && editingId !== s.id && (
              <div className="mr-2 flex shrink-0 items-center gap-1">
                {onReuse && (
                  <button
                    onClick={() => onReuse(s.id)}
                    title="再来一次（基于此行程创建新会话）"
                    className="hidden h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-green-50 hover:text-green-600 group-hover:flex"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                      <path d="M21 3v5h-5" />
                    </svg>
                  </button>
                )}
                <button
                  onClick={() => startRename(s)}
                  title="重命名会话"
                  className="hidden h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-600 group-hover:flex"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                <button
                  onClick={() => setPendingDelete(s)}
                  title="删除会话"
                  className="hidden h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-red-50 hover:text-red-500 group-hover:flex"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 批量删除底部栏 */}
      {batchMode && selectedIds.size > 0 && (
        <div className="border-t border-gray-200 p-3 bg-gray-50">
          <div className="text-xs text-gray-500 mb-2">已选中 {selectedIds.size} 个会话</div>
          <button
            onClick={confirmBatchDelete}
            className="w-full rounded-xl bg-red-600 py-2.5 text-sm font-medium text-white hover:bg-red-700"
          >
            删除选中
          </button>
        </div>
      )}

      {/* 删除确认弹窗 */}
      {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="mx-4 w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-gray-800">删除会话</h3>
            <p className="mt-2 text-sm text-gray-500">
              确定要删除「{pendingDelete.title}」吗？该会话的消息和行程将一并删除，且无法恢复。
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setPendingDelete(null)}
                className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
              >
                取消
              </button>
              <button
                onClick={confirmDelete}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
