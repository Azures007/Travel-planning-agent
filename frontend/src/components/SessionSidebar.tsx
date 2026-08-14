import { useState } from 'react'
import type { SessionInfo } from '../lib/types'

interface SessionSidebarProps {
  sessions: SessionInfo[]
  activeId: number | null
  onNew: () => void
  onSelect: (id: number) => void
  onDelete: (id: number) => void
  onRename: (id: number, title: string) => void
}

export default function SessionSidebar({ sessions, activeId, onNew, onSelect, onDelete, onRename }: SessionSidebarProps) {
  // 待确认删除的会话（null = 未弹出弹窗）
  const [pendingDelete, setPendingDelete] = useState<SessionInfo | null>(null)
  // 正在重命名的会话 id + 输入值
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')

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

  return (
    <div className="flex w-60 flex-col border-r border-gray-200 bg-white">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full rounded-xl bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          ＋ 新建行程
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-gray-400">暂无历史会话</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`group mb-1 flex items-center rounded-lg transition-colors ${
              activeId === s.id ? 'bg-blue-50' : 'hover:bg-gray-50'
            }`}
          >
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
                onClick={() => onSelect(s.id)}
                onDoubleClick={() => startRename(s)}
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
            {editingId !== s.id && (
              <div className="mr-2 flex shrink-0 items-center gap-1">
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
