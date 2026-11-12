"""测试夹具：内存 SQLite + 测试会话"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401 — 确保所有模型被注册

# 测试环境强制关闭检索重排序：防止 .env 开启后单测经网络调用真实 rerank 档
settings.RAG_RERANK_ENABLED = False
# 测试环境默认关闭 JEV：防止 .env 配了真实 Key 后单测联网；JEV 专项用例自行开启
settings.JEV_ENABLED = False


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    """每个测试函数独立的内存数据库会话"""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
