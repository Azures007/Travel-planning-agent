"""Checkpointer 单例：根据数据库类型选择合适的 Saver。

支持 SQLite (AsyncSqliteSaver) 和 PostgreSQL (AsyncPostgresSaver)。
"""

import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_checkpointer = None
_initialized = False
_setup_lock = asyncio.Lock()


async def get_checkpointer():
    """返回合适的 checkpointer 单例（首次调用时建表）。"""
    global _checkpointer, _initialized

    if _checkpointer is not None:
        return _checkpointer

    async with _setup_lock:
        if _checkpointer is not None:  # 双检锁
            return _checkpointer

        db_url = settings.database_url

        # 根据数据库类型选择 checkpointer
        if db_url.startswith("sqlite"):
            # SQLite: 使用 AsyncSqliteSaver（持久化）
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            import aiosqlite

            # 提取数据库文件路径
            db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("./", "")

            conn = await aiosqlite.connect(db_path)
            _checkpointer = AsyncSqliteSaver(conn)
            await _checkpointer.setup()
            logger.info("AsyncSqliteSaver checkpointer 初始化完成（数据库: %s）", db_path)

        else:
            # PostgreSQL: 使用 AsyncPostgresSaver
            import sys
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            conninfo = db_url.replace("postgresql+asyncpg://", "postgresql://")
            pool = AsyncConnectionPool(
                conninfo,
                kwargs={"row_factory": dict_row, "autocommit": True},
                open=False,
            )
            await pool.open()
            _checkpointer = AsyncPostgresSaver(pool)
            await _checkpointer.setup()
            logger.info("AsyncPostgresSaver checkpointer 初始化完成")

        _initialized = True
        return _checkpointer
