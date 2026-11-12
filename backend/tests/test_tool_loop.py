"""OpenAIToolLoop 多轮工具闭环测试。"""
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

from app.agents.tool_loop import MAX_TOOL_ROUNDS, OpenAIToolLoop


class FakeAsyncStream:
    """模拟 OpenAI SDK 的异步流。"""

    def __init__(self, content: str):
        self._content = content

    def __aiter__(self):
        return self._chunks()

    async def _chunks(self):
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=self._content))]
        )


def _tool_call(call_id: str, arguments: str, name: str = "query_material_history"):
    """构造一条 OpenAI 风格的工具调用。"""
    return SimpleNamespace(
        id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


def _assistant(tool_calls=None, content=None):
    """构造 assistant 决策响应，保留供应商思考字段。"""
    return SimpleNamespace(
        role="assistant",
        content=content,
        reasoning_content="需要查询长期材料记录。",
        tool_calls=tool_calls or [],
    )


class ScriptedToolLLM:
    """按脚本顺序返回决策响应；stream=True 时返回固定流式文本。"""

    model_name = "deepseek-reasoner"

    def __init__(self, decisions: list, final_text: str = "最终回答"):
        self._decisions = list(decisions)
        self._final_text = final_text
        self.calls = []
        self.async_client = SimpleNamespace(chat=SimpleNamespace(completions=self))

    async def create(self, **kwargs):
        # 消息列表按次快照：闭环会持续向同一 payload 追加轮次消息，
        # 存引用会观察到后续轮次的最终状态而非调用时刻的状态
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if kwargs["stream"] is False:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=self._decisions.pop(0))]
            )
        return FakeAsyncStream(self._final_text)


def _tool(recorded: list):
    """创建记录调用参数的长期材料查询工具（签名与真实工具一致）。"""

    async def query(
        material_name: str | None = None,
        supplier_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        kwargs = {"material_name": material_name, "supplier_name": supplier_name,
                  "date_from": date_from, "date_to": date_to}
        recorded.append({k: v for k, v in kwargs.items() if v is not None})
        return f"记录：{material_name}"

    return StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )


async def test_multi_round_executes_tools_until_cap():
    """三轮都要求工具时连续执行，轮次用尽走安全阀流式收尾。"""
    recorded: list[dict] = []
    llm = ScriptedToolLLM([
        _assistant(tool_calls=[_tool_call("call-1", '{"material_name":"桂花"}')]),
        _assistant(tool_calls=[_tool_call("call-2", '{"material_name":"银杏"}')]),
        _assistant(tool_calls=[_tool_call("call-3", '{"supplier_name":"示例苗木"}')]),
    ])
    loop = OpenAIToolLoop(llm, [_tool(recorded)])
    chunks = [
        chunk async for chunk in loop.stream(
            [HumanMessage(content="桂花的历史成交价")], required_tool="query_material_history"
        )
    ]

    assert chunks == ["最终回答"]
    assert recorded == [
        {"material_name": "桂花"},
        {"material_name": "银杏"},
        {"supplier_name": "示例苗木"},
    ]
    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1
    # 第二轮决策请求携带第一轮的原始 assistant 消息与 tool 结果
    second = llm.calls[1]["messages"]
    assert second[-2]["reasoning_content"] == "需要查询长期材料记录。"
    assert second[-2]["tool_calls"][0]["id"] == "call-1"
    assert second[-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "记录：桂花",
    }
    # 安全阀收尾请求包含第三轮工具结果，且不再携带 tools
    final = llm.calls[-1]
    assert "tools" not in final
    assert final["messages"][-1]["tool_call_id"] == "call-3"


async def test_plain_answer_after_tool_result_streams_directly():
    """模型拿到工具结果后给出文本回答时直接输出，不再进入安全阀。"""
    recorded: list[dict] = []
    llm = ScriptedToolLLM([
        _assistant(tool_calls=[_tool_call("call-1", '{"material_name":"桂花"}')]),
        _assistant(content="根据记录，桂花成交价 100 元/株。"),
    ])
    loop = OpenAIToolLoop(llm, [_tool(recorded)])
    chunks = [
        chunk async for chunk in loop.stream(
            [HumanMessage(content="桂花的历史成交价")], required_tool="query_material_history"
        )
    ]

    assert chunks == ["根据记录，桂花成交价 100 元/株。"]
    assert len(llm.calls) == 2
    assert recorded == [{"material_name": "桂花"}]


async def test_required_tool_nudges_then_uses_tool():
    """首轮未调工具时注入用户角色提醒，次轮模型改调工具并依据结果回答。"""
    recorded: list[dict] = []
    llm = ScriptedToolLLM([
        _assistant(content="桂花很常见，无需查询。"),
        _assistant(tool_calls=[_tool_call("call-1", '{"material_name":"桂花"}')]),
        _assistant(content="根据记录，桂花成交价 100 元/株。"),
    ])
    loop = OpenAIToolLoop(llm, [_tool(recorded)])
    chunks = [
        chunk async for chunk in loop.stream(
            [HumanMessage(content="桂花的历史成交价")], required_tool="query_material_history"
        )
    ]

    assert chunks == ["根据记录，桂花成交价 100 元/株。"]
    assert recorded == [{"material_name": "桂花"}]
    assert len(llm.calls) == 3
    nudge = llm.calls[1]["messages"][-1]
    assert nudge["role"] == "user"
    assert "query_material_history" in nudge["content"]
    # 提醒前保留了模型首轮原始 assistant 消息（含思考字段），协议可回放
    assert llm.calls[1]["messages"][-2]["reasoning_content"] == "需要查询长期材料记录。"


async def test_required_tool_suppresses_answer_without_any_tool_call():
    """提醒重试后模型仍不调用工具时，不输出自答内容，交由调用方降级。"""
    recorded: list[dict] = []
    llm = ScriptedToolLLM([
        _assistant(content="桂花很常见，无需查询。"),
        _assistant(content="桂花的价格需要查询记录。"),
        _assistant(content="我没有查到相关记录。"),
    ])
    loop = OpenAIToolLoop(llm, [_tool(recorded)])
    chunks = [
        chunk async for chunk in loop.stream(
            [HumanMessage(content="桂花的历史成交价")], required_tool="query_material_history"
        )
    ]

    assert chunks == []
    assert loop.last_results == {}
    assert recorded == []
    assert len(llm.calls) == MAX_TOOL_ROUNDS


async def test_unknown_tool_name_raises():
    """模型返回未注册的工具名时报错，不静默吞掉。"""
    llm = ScriptedToolLLM([
        _assistant(tool_calls=[_tool_call("call-1", "{}", name="no_such_tool")]),
    ])
    loop = OpenAIToolLoop(llm, [_tool([])])
    with pytest.raises(ValueError):
        [chunk async for chunk in loop.stream([HumanMessage(content="查询")])]
