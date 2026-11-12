"""数据库异步引擎与会话工厂"""
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base

# 异步引擎（WAL 模式 + 外键约束由 connect 事件设置；连接池参数供多 worker 部署调优）
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_ENV == "development"),
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    """连接时启用 WAL 模式与外键约束（SQLite 特有配置）"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    # 写并发时最多等待 10 秒拿写锁，而不是立即报 database is locked
    cursor.execute("PRAGMA busy_timeout=10000")
    # WAL 下安全且更快的落盘策略（换更高写吞吐）
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# 会话工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：提供数据库会话，请求结束后自动关闭"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """应用启动时创建所有表（开发环境用；生产环境用 alembic upgrade head）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
