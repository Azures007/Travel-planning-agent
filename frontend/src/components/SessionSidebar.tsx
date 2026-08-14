import type { SessionInfo } from '../lib/types'

interface SessionSidebarProps {
  sessions: SessionInfo[]
  activeId: number | null
  onNew: () => void
  onSelect: (id: number) => void
  onDelete: (id: number) => void
}

export default function SessionSidebar({ sessions, activeId, onNew, onSelect, onDelete }: SessionSidebarProps) {
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
            <button
              onClick={() => onSelect(s.id)}
              className={`flex-1 truncate px-3 py-2.5 text-left text-sm ${
                activeId === s.id ? 'text-blue-700' : 'text-gray-700'
              }`}
            >
              <div className="truncate font-medium">{s.title}</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '会话'}
              </div>
            </button>
            <button
              onClick={() => onDelete(s.id)}
              title="删除会话"
              className="mr-2 hidden h-6 w-6 shrink-0 items-center justify-center rounded text-gray-400 hover:bg-red-50 hover:text-red-500 group-hover:flex"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
