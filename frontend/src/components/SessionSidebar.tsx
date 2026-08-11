import type { SessionInfo } from '../lib/types'

interface SessionSidebarProps {
  sessions: SessionInfo[]
  activeId: number | null
  onNew: () => void
  onSelect: (id: number) => void
}

export default function SessionSidebar({ sessions, activeId, onNew, onSelect }: SessionSidebarProps) {
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
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`mb-1 w-full rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
              activeId === s.id
                ? 'bg-blue-50 text-blue-700'
                : 'text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div className="truncate font-medium">{s.title}</div>
            <div className="text-xs text-gray-400 mt-0.5">
              {s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '会话'}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
