export default function TimelineSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto bg-white">
      <div className="max-w-2xl mx-auto p-6 animate-pulse">
        {/* 标题卡片骨架 */}
        <div className="rounded-2xl bg-gradient-to-r from-gray-200 to-gray-300 p-6 mb-6">
          <div className="h-8 bg-white/40 rounded w-2/3 mb-3"></div>
          <div className="h-4 bg-white/30 rounded w-1/2 mb-4"></div>
          <div className="flex gap-2">
            <div className="h-6 bg-white/30 rounded-full w-24"></div>
            <div className="h-6 bg-white/30 rounded-full w-32"></div>
            <div className="h-6 bg-white/30 rounded-full w-28"></div>
          </div>
        </div>

        {/* 天数骨架 */}
        {[1, 2, 3].map((day) => (
          <div key={day} className="relative pl-10 mb-8">
            {/* 时间线圆点 */}
            <div className="absolute left-0 top-2 w-6 h-6 rounded-full bg-gray-200"></div>

            {/* 天数标题 */}
            <div className="h-6 bg-gray-200 rounded w-32 mb-4"></div>

            {/* 活动列表 */}
            <div className="space-y-3">
              {[1, 2, 3].map((act) => (
                <div key={act} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <div className="h-5 bg-gray-200 rounded w-3/4 mb-2"></div>
                      <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                    </div>
                    <div className="h-4 bg-gray-200 rounded w-16"></div>
                  </div>
                  <div className="h-3 bg-gray-200 rounded w-full mt-2"></div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
