"""LLM 日志服务测试"""
import pytest

from app.services.llm_logger import LLMCallLogger


pytestmark = pytest.mark.asyncio


async def test_log_success(db):
    """正常写入不抛出异常"""
    await LLMCallLogger.log(
        agent_name="TestAgent",
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        cost=0.001,
        latency_ms=200,
        cache_hit=False,
        session_id="sess-001",
        db=db,
    )


async def test_log_does_not_raise_on_bad_db(db):
    """DB 异常不阻断主链路（静默降级）"""
    await db.close()
    # 不应抛出异常
    await LLMCallLogger.log(
        agent_name="TestAgent",
        model="test-model",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        latency_ms=0,
        cache_hit=False,
        session_id="",
        db=db,
    )


async def test_summary_by_model_empty(db):
    result = await LLMCallLogger.summary_by_model(7, db)
    assert result == []


async def test_summary_after_log(db):
    await LLMCallLogger.log(
        agent_name="SummaryTest",
        model="gpt-4o",
        input_tokens=200,
        output_tokens=100,
        cost=0.01,
        latency_ms=500,
        cache_hit=False,
        session_id="s1",
        db=db,
    )
    await db.flush()
    result = await LLMCallLogger.summary_by_model(7, db)
    assert any(r.key == "gpt-4o" for r in result)
