"""Checkpointer 单例：AsyncPostgresSaver 懒初始化。

Windows 上 psycopg 3 的 async 模式不兼容默认的 ProactorEventLoop，
必须在进入 asyncio 前设置 WindowsSelectorEventLoopPolicy（见 module 底部）。
"""

import asyncio
import sys

# psycopg 3 async 模式需要 selector 事件循环（Windows）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer = None  # AsyncPostgresSaver 实例（延迟导入避免循环依赖）
_initialized = False
_setup_lock = asyncio.Lock()


def psycopg_conninfo() -> str:
    """把 SQLAlchemy 的 asyncpg 连接串转成 psycopg 需要的 postgresql:// 格式。"""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def get_checkpointer():
    """返回 AsyncPostgresSaver 单例（首次调用时建表）。"""
    global _pool, _checkpointer, _initialized

    if _checkpointer is not None:
        return _checkpointer

    async with _setup_lock:
        if _checkpointer is not None:  # 双检锁，防并发重复初始化
            return _checkpointer

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        conninfo = psycopg_conninfo()
        _pool = AsyncConnectionPool(
            conninfo,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=False,
        )
        await _pool.open()

        _checkpointer = AsyncPostgresSaver(_pool)
        await _checkpointer.setup()
        _initialized = True
        logger.info("AsyncPostgresSaver checkpointer 初始化完成")
        return _checkpointer
