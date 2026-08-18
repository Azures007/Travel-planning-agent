"""请求日志、性能监控与限流中间件。"""

import logging
import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个请求的方法、路径、状态码、耗时，并注入请求 ID。

    - 为每个请求生成短 request_id，方便日志关联
    - 记录慢请求（>3s）为 warning
    - 响应头带上 X-Request-ID 和 X-Process-Time
    """

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.perf_counter() - start
            logger.exception(
                f"[{request_id}] {request.method} {request.url.path} "
                f"崩溃 耗时={elapsed:.2f}s"
            )
            raise

        elapsed = time.perf_counter() - start

        # 慢请求告警
        log_fn = logger.warning if elapsed > 3.0 else logger.info
        log_fn(
            f"[{request_id}] {request.method} {request.url.path} "
            f"-> {response.status_code} 耗时={elapsed:.3f}s"
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed:.3f}"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于滑动窗口的简单限流中间件。

    - 按客户端 IP 限流，默认每分钟 120 次请求
    - 超限返回 429，并带上 Retry-After 头
    - 仅对 /api/ 路径生效，健康检查等不限流

    注：这是进程级内存限流，适合单实例开发/小规模部署。
    生产多实例应使用 Redis 等共享存储。
    """

    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        # {ip: deque[timestamp]}
        self._requests: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        # 只对 API 路径限流
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = self._requests[client_ip]

        # 移除窗口外的旧请求记录
        while bucket and bucket[0] < now - self.window:
            bucket.popleft()

        # 超过限制
        if len(bucket) >= self.max_requests:
            retry_after = int(self.window - (now - bucket[0])) + 1
            logger.warning(f"限流触发: {client_ip} 超过 {self.max_requests}/{self.window}s")
            return JSONResponse(
                status_code=429,
                content={"detail": f"请求过于频繁，请 {retry_after} 秒后重试"},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)
