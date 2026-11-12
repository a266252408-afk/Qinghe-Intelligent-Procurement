"""ChatAgent 长期材料查询工具测试。"""
import json
from datetime import date
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.tools import StructuredTool

from app.agents.chat import (
    ChatAgent,
    _empty_records,
    _extract_material_name,
    _format_material_history_result,
)


def test_extract_material_name_from_history_question():
    """历史价格问题只提取关键词，不把问题文本传给结构化查询。"""
    assert _extract_material_name("桂花的历史成交价") == "桂花"
    assert _extract_material_name("请查询香樟历史报价") == "香樟"
    assert _extract_material_name("/历史 桂花") == "桂花"
    # 词表与意图门控同步：裸"成交价/报价"与"上次买的 X"句式要能提出关键词
    assert _extract_material_name("示例苗木的成交价是什么?") == "示例苗木"
    assert _extract_material_name("香樟的成交价") == "香樟"
    assert _extract_material_name("示例园林的报价") == "示例园林"
    assert _extract_material_name("上个月桂花的成交价") == "桂花"
    assert _extract_material_name("上次买的桂花多少钱") == "桂花"


def test_format_material_history_result_without_llm():
    """模型整理失败时仍能展示结构化长期记录。"""
    raw = '[{"supplier_name":"示例园林","spec":"高2m","quote_price":520,"final_price":500,"quote_date":"2026-08-25"}]'
    answer = _format_material_history_result(raw)
    assert "示例园林" in answer
    assert "报价 520" in answer
    assert "成交价 500" in answer


class FakeStreamLLM:
    """模拟普通对话流式模型。"""

    def __init__(self):
        self.stream_messages = None

    async def astream(self, messages):
        self.stream_messages = messages
        yield AIMessageChunk(content="历史价格是 100 元。")


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


def _tool_response():
    """构造带思考字段和原始 tool-call-id 的模型响应。"""
    function = SimpleNamespace(
        name="query_material_history",
        arguments='{"material_name":"桂花"}',
    )
    call = SimpleNamespace(id="call-123", type="function", function=function)
    message = SimpleNamespace(
        role="assistant",
        content=None,
        reasoning_content="需要查询长期材料记录。",
        tool_calls=[call],
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeToolLLM:
    """模拟带 OpenAI 兼容异步客户端的模型。"""

    model_name = "deepseek-reasoner"

    def __init__(self, final_error: Exception | None = None):
        self.calls = []
        self.final_error = final_error
        self.async_client = SimpleNamespace(chat=SimpleNamespace(completions=self))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["stream"] is False:
            return _tool_response()
        if self.final_error:
            raise self.final_error
        return FakeAsyncStream("已查询到桂花成交价 120 元/株。")


async def test_history_query_falls_back_to_records_when_llm_fails():
    """工具已执行但最终模型失败时，仍返回确定性结构化结果。"""
    async def query(material_name: str) -> str:
        return '[{"supplier_name":"示例园林","spec":"高2m","quote_price":520,"final_price":500,"quote_date":"2026-08-25"}]'

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = FakeToolLLM(RuntimeError("reasoning_content is required"))
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, [], tool, {"material_name": "桂花"}
    )]

    assert "AI 服务暂时不可用" not in chunks[0]
    assert "成交价 500" in chunks[0]


async def test_history_tool_result_is_sent_back_to_model():
    """工具结果按标准 tool 消息回传，并保留 reasoning_content 和调用 ID。"""

    async def query(material_name: str) -> str:
        return "银杏，成交价 100 元/株"

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = FakeToolLLM()
    chunks = [
        chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, [], tool, {"material_name": "桂花"}
        )
    ]

    assert chunks == ["已查询到桂花成交价 120 元/株。"]
    # 多轮闭环下为 3 次调用：第 1/2 轮决策请求 + 安全阀流式收尾；取前两次验证回传协议
    first, second = llm.calls[:2]
    assert first["tool_choice"] == "auto"
    assistant = second["messages"][-2]
    tool_result = second["messages"][-1]
    assert assistant["reasoning_content"] == "需要查询长期材料记录。"
    assert assistant["tool_calls"][0]["id"] == "call-123"
    assert tool_result == {
        "role": "tool",
        "tool_call_id": "call-123",
        "content": "银杏，成交价 100 元/株",
    }


async def test_history_question_requests_tool_before_model_answer():
    """命中历史问题时，使用供应商兼容的 auto 选择请求长期工具。"""
    async def query(material_name: str) -> str:
        return "桂花，成交价 120 元/株"

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = FakeToolLLM()
    chunks = [
        chunk async for chunk in ChatAgent()._stream_with_optional_tool(
            llm, [], tool, {"material_name": "桂花"}
        )
    ]

    assert chunks == ["已查询到桂花成交价 120 元/株。"]
    assert llm.calls[0]["tool_choice"] == "auto"


async def test_history_tool_rejects_material_name_mismatch():
    """模型参数与用户材料名不一致时不得查询错误材料。"""
    calls = []

    async def query(material_name: str) -> str:
        calls.append(material_name)
        return "不应被调用"

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = FakeToolLLM()
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, [], tool, {"material_name": "银杏"}
    )]

    assert chunks == ["已查询到桂花成交价 120 元/株。"]
    assert calls == []
    assert "与当前用户问题不一致" in llm.calls[1]["messages"][-1]["content"]


async def test_normal_chat_does_not_bind_or_call_history_tool():
    """普通对话直接走流式模型，不绑定长期记忆工具。"""
    llm = FakeStreamLLM()
    async def unused_tool(material_name: str) -> str:
        return material_name

    tool = StructuredTool.from_function(
        coroutine=unused_tool,
        name="query_material_history",
        description="查询长期材料历史",
    )
    chunks = [
        chunk async for chunk in ChatAgent()._stream_with_optional_tool(
            llm, [], None
        )
    ]

    assert chunks == ["历史价格是 100 元。"]


def _records_json() -> str:
    """构造一条可格式化的长期记录 JSON。"""
    return '[{"supplier_name":"示例园林","spec":"高2m","quote_price":520,"final_price":500,"quote_date":"2026-08-25"}]'


class ScriptedChatLLM:
    """按脚本返回决策响应，用于验证多轮参数透传与文本收尾。"""

    model_name = "deepseek-reasoner"

    def __init__(self, decisions: list, final_text: str = "根据记录整理的回答。"):
        self._decisions = list(decisions)
        self._final_text = final_text
        self.calls = []
        self.async_client = SimpleNamespace(chat=SimpleNamespace(completions=self))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["stream"] is False:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=self._decisions.pop(0))]
            )
        return FakeAsyncStream(self._final_text)


def _chat_tool_call(arguments: str, call_id: str = "call-1"):
    """构造长期材料工具调用。"""
    function = SimpleNamespace(name="query_material_history", arguments=arguments)
    return SimpleNamespace(id=call_id, type="function", function=function)


def _chat_assistant(tool_calls=None, content=None):
    """构造 assistant 决策响应。"""
    return SimpleNamespace(
        role="assistant", content=content, reasoning_content="思考中", tool_calls=tool_calls or []
    )


async def test_model_chosen_args_pass_through_without_lock():
    """模型自选的查询参数（含供应商）原样透传给工具，不再被服务端锁定。"""
    recorded = []

    async def query(
        material_name: str | None = None,
        supplier_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        kwargs = {"material_name": material_name, "supplier_name": supplier_name,
                  "date_from": date_from, "date_to": date_to}
        recorded.append({k: v for k, v in kwargs.items() if v is not None})
        return _records_json()

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = ScriptedChatLLM([
        _chat_assistant(tool_calls=[_chat_tool_call('{"material_name":"桂花","supplier_name":"示例园林"}')]),
        _chat_assistant(content="根据记录回答"),
    ])
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, [], tool
    )]

    assert chunks == ["根据记录回答"]
    assert recorded == [{"material_name": "桂花", "supplier_name": "示例园林"}]


async def test_tool_returns_retryable_error_for_bad_date():
    """日期格式非法时返回可自纠的错误 JSON，供模型下一轮修正。"""
    tool = ChatAgent()._build_material_history_tool(team_id=1, db=None)
    raw = await tool.coroutine(material_name="桂花", date_from="2026/01/01")

    assert "YYYY-MM-DD" in json.loads(raw)["error"]


async def test_tool_empty_result_hints_supplier_switch(db):
    """真实场景复现：材料名"示例苗木"查空但匹配供应商，工具返回换字段指引。

    线上案例：模型拿到裸 [] 后自己猜到"可能是供应商"却不会换字段重查。
    指引必须出现在工具结果里（模型决策点上），而不是只写在 system prompt。
    """
    from app.models.material_history import MaterialHistoryRecord

    db.add(MaterialHistoryRecord(
        team_id=7, supplier_name="示例苗木", material_name="桂花",
        spec="地径8-10cm", unit="株", quantity=1.0, quote_price=500.0,
        quote_date=date(2026, 8, 11), source_file="报价.csv",
        uploaded_by=1, fingerprint="fp-hint-1",
    ))
    await db.commit()

    tool = ChatAgent()._build_material_history_tool(team_id=7, db=db)

    raw = await tool.coroutine(material_name="示例苗木")
    data = json.loads(raw)
    assert data["results"] == []
    assert data["supplier_match"] == ["示例苗木"]
    assert "supplier_name" in data["hint"]

    # 模型按指引换字段后能查到记录本体
    records = json.loads(await tool.coroutine(supplier_name="示例苗木"))
    assert isinstance(records, list)
    assert records[0]["supplier_name"] == "示例苗木"
    assert records[0]["material_name"] == "桂花"


def test_empty_records_accepts_hint_object():
    """判空函数同时识别空列表与带指引的空结果对象。"""
    assert _empty_records('{"results": []}') is True
    assert _empty_records('[]') is True
    assert _empty_records('[{"supplier_name":"示例园林"}]') is False
    assert _empty_records('{"error": "boom"}') is False
    assert _empty_records('not-json') is False


def test_format_material_history_result_with_hint_dict():
    """带指引的空结果对象在降级链中直接展示指引文本。"""
    raw = json.dumps({
        "results": [],
        "hint": "材料名“示例苗木”未查到记录，但匹配到供应商，请改用 supplier_name 查询。",
        "supplier_match": ["示例苗木"],
    }, ensure_ascii=False)
    answer = _format_material_history_result(raw)

    assert "supplier_name" in answer
    assert "示例苗木" in answer


async def test_history_falls_back_to_direct_tool_query_when_model_skips_tool():
    """模型经提醒仍未调工具时丢弃自答，正则提参直查工具并格式化输出。"""
    async def query(
        material_name: str | None = None,
        supplier_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        return _records_json()

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = ScriptedChatLLM([
        _chat_assistant(content="桂花很常见，无需查询记录。"),
        _chat_assistant(content="桂花的价格需要查询。"),
        _chat_assistant(content="我没有查到记录。"),
    ])
    messages = [HumanMessage(content="桂花的历史成交价")]
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, messages, tool
    )]

    assert len(chunks) == 1
    assert "示例园林" in chunks[0]
    assert "无需查询" not in chunks[0]


async def test_fallback_queries_supplier_when_material_empty():
    """降级时材料名查空自动换供应商名再查（"××苗木"是供应商的典型形态）。"""
    recorded = []

    async def query(
        material_name: str | None = None,
        supplier_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        kwargs = {"material_name": material_name, "supplier_name": supplier_name,
                  "date_from": date_from, "date_to": date_to}
        recorded.append({k: v for k, v in kwargs.items() if v is not None})
        if material_name:
            return "[]"
        return _records_json()

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = ScriptedChatLLM([
        _chat_assistant(content="自答一。"),
        _chat_assistant(content="自答二。"),
        _chat_assistant(content="自答三。"),
    ])
    messages = [HumanMessage(content="示例苗木的成交价是什么")]
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, messages, tool
    )]

    assert recorded == [{"material_name": "示例苗木"}, {"supplier_name": "示例苗木"}]
    assert "示例园林" in chunks[0]


async def test_net_overrides_model_answer_when_all_results_empty():
    """模型查空后放弃时，其"未找到"回答被确定性降级接管，返回供应商记录。

    线上复测的故障模式：模型按 material_name 查空后不换字段，直接回答未找到。
    """
    recorded = []

    async def query(
        material_name: str | None = None,
        supplier_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        kwargs = {"material_name": material_name, "supplier_name": supplier_name,
                  "date_from": date_from, "date_to": date_to}
        recorded.append({k: v for k, v in kwargs.items() if v is not None})
        if material_name:
            return '{"results": [], "hint": "未查到记录，可改用 supplier_name。"}'
        return _records_json()

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = ScriptedChatLLM([
        _chat_assistant(tool_calls=[_chat_tool_call('{"material_name":"示例苗木"}')]),
        _chat_assistant(content="未找到示例苗木的记录，请提供苗木品种名称。"),
    ])
    messages = [HumanMessage(content="示例苗木的成交价是什么")]
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, messages, tool
    )]

    assert "示例园林" in chunks[0]
    assert "未找到" not in chunks[0]
    # 模型的 material 查询 + 降级链的 material/supplier 两次查询
    assert recorded[-1] == {"supplier_name": "示例苗木"}
    assert len(recorded) == 3


async def test_history_prompts_for_material_name_when_model_skips_tool():
    """提不出关键词且模型未调工具时，提示用户补充。"""
    async def query(
        material_name: str | None = None,
        supplier_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        return "[]"

    tool = StructuredTool.from_function(
        coroutine=query,
        name="query_material_history",
        description="查询长期材料历史",
    )
    llm = ScriptedChatLLM([
        _chat_assistant(content="请告诉我具体材料。"),
        _chat_assistant(content="请说明材料。"),
        _chat_assistant(content="需要材料名。"),
    ])
    messages = [HumanMessage(content="/历史")]
    chunks = [chunk async for chunk in ChatAgent()._stream_with_optional_tool(
        llm, messages, tool
    )]

    assert chunks == ["请提供需要查询的材料名称。"]


def test_material_history_tool_input_requires_any_condition():
    """工具参数至少要有一个筛选条件，防止无条件全量拉取。"""
    from pydantic import ValidationError

    from app.schemas.chat import MaterialHistoryToolInput

    with pytest.raises(ValidationError):
        MaterialHistoryToolInput()
    assert MaterialHistoryToolInput(material_name="桂花").material_name == "桂花"
    assert MaterialHistoryToolInput(supplier_name="示例园林").supplier_name == "示例园林"
