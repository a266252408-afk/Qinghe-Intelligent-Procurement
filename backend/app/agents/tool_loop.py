"""OpenAI 兼容工具调用闭环，保留供应商思考字段和原始调用 ID。"""
import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 决策请求轮次上限：超过后进入安全阀（无 tools 流式收尾），防止无界工具循环
MAX_TOOL_ROUNDS = 3

# 模型未调用必需工具时注入的用户角色提醒，给模型一次自主纠偏的机会
_TOOL_NUDGE = (
    "系统提示：用户的问题需要查询长期材料记录。请现在调用 {tool} 工具获取数据，"
    "再依据工具返回的结果回答；不要凭记忆或常识直接回答。"
)


class OpenAIToolLoop:
    """执行多轮 assistant tool_calls ⇄ tool 闭环，轮次用尽后安全阀流式收尾。"""

    def __init__(
        self,
        llm: Any,
        tools: list[BaseTool],
        session_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        """初始化适配器；llm 必须由 LLMFactory 返回并暴露 async_client。"""
        self._llm = llm
        self._tools = {tool.name: tool for tool in tools}
        self._tool_specs = [convert_to_openai_tool(tool) for tool in tools]
        self._session_id = session_id
        self._db = db
        self.last_results: dict[str, str] = {}

    async def stream(
        self,
        messages: list[BaseMessage],
        required_tool: str | None = None,
        expected_tool_args: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """执行多轮工具调用：模型可持续追加 tool_calls，至多 MAX_TOOL_ROUNDS 轮。

        每轮决策请求都携带 tools（tool_choice=auto）；模型不再调用工具时直接输出
        内容返回。指定 required_tool 而模型一轮都未调用工具时，注入用户角色提醒
        再给下一轮机会；轮次用尽仍未调用则静默返回（last_results 为空），由调用方
        走确定性降级。轮次用尽仍要求工具时走安全阀——发送不带 tools 的流式最终
        请求强制生成文本回答。
        """
        payload = _serialize_messages(messages)
        tool_executed = False
        for round_index in range(MAX_TOOL_ROUNDS):
            response = await self._request(payload, required_tool)
            assistant = response.choices[0].message
            payload.append(_serialize_assistant_response(assistant))
            tool_calls = getattr(assistant, "tool_calls", None) or []
            if not tool_calls:
                if tool_executed:
                    content = _message_content(getattr(assistant, "content", ""))
                    if content:
                        yield content
                    return
                if required_tool and round_index < MAX_TOOL_ROUNDS - 1:
                    payload.append({
                        "role": "user",
                        "content": _TOOL_NUDGE.format(tool=required_tool),
                    })
                    continue
                # 轮次用尽仍未调用必需工具：不输出未经验证的自答，交调用方降级
                return
            await self._append_tool_results(payload, tool_calls, expected_tool_args)
            tool_executed = True
        async for delta in self._stream_final(payload):
            yield delta

    async def _request(
        self,
        messages: list[dict[str, Any]],
        required_tool: str | None,
    ) -> Any:
        """发送非流式工具决策请求，确保原始响应可被完整保存。"""
        client = self._get_completions_client()
        kwargs: dict[str, Any] = {
            "model": self._llm.model_name,
            "messages": messages,
            "tools": self._tool_specs,
            "stream": False,
        }
        if required_tool:
            # DeepSeek 思考模式不接受强制 function tool_choice；当前只注册目标工具，
            # 使用 auto 仍可保持标准协议并避免供应商 400。
            kwargs["tool_choice"] = "auto"
        from app.services.llm_gate import LLMGate
        started_at = time.monotonic()
        try:
            async with LLMGate.acquire("medium"):
                response = await client.create(**kwargs)
        except Exception:
            await self._log_call(None, started_at)
            raise
        await self._log_call(response, started_at)
        return response

    async def _stream_final(
        self,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """发送工具结果后的最终回答请求，保留 SSE 输出。"""
        from app.services.llm_gate import LLMGate
        client = self._get_completions_client()
        started_at = time.monotonic()
        try:
            # 并发闸门覆盖整个流式消费过程，直到读完最后一个分片才释放名额
            async with LLMGate.acquire("medium"):
                for attempt in range(1, 3):  # 至多 2 次：仅在未输出内容时重试瞬时错误
                    emitted = False
                    try:
                        stream = await client.create(
                            model=self._llm.model_name,
                            messages=messages,
                            stream=True,
                        )
                        async for chunk in stream:
                            choices = getattr(chunk, "choices", None) or []
                            if not choices:
                                continue
                            delta = getattr(choices[0], "delta", None)
                            content = _message_content(getattr(delta, "content", ""))
                            if content:
                                emitted = True
                                yield content
                        break
                    except Exception as exc:
                        if emitted or attempt >= 2:
                            raise
                        logger.warning("工具闭环流式连接建立失败，退避后重试一次：%s", exc)
                        await asyncio.sleep(1)
        finally:
            await self._log_call(None, started_at)

    async def _log_call(self, response: Any, started_at: float) -> None:
        """记录一次原始 API 调用；日志失败不阻断工具闭环。"""
        if self._db is None or self._session_id is None:
            return
        from app.services.llm_logger import LLMCallLogger

        usage = getattr(response, "usage", None)
        try:
            await LLMCallLogger.log(
                agent_name="ChatAgent.tool_loop",
                model=getattr(self._llm, "model_name", "unknown"),
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                cost=0.0,
                latency_ms=int((time.monotonic() - started_at) * 1000),
                cache_hit=False,
                session_id=self._session_id,
                db=self._db,
            )
        except Exception as exc:
            logger.warning("工具调用 LLM 日志记录失败：%s", exc)

    async def _append_tool_results(
        self,
        payload: list[dict[str, Any]],
        tool_calls: list[Any],
        expected_tool_args: dict[str, Any] | None,
    ) -> None:
        """按模型返回的原始 ID 逐个执行工具并追加 tool 消息。"""
        for tool_call in tool_calls:
            call_id = getattr(tool_call, "id", None)
            function = getattr(tool_call, "function", None)
            name = getattr(function, "name", None)
            if not call_id or name not in self._tools:
                raise ValueError("模型返回了未知或缺少 ID 的工具调用")
            content = await self._invoke_tool(
                name, getattr(function, "arguments", "{}"), expected_tool_args
            )
            payload.append({"role": "tool", "tool_call_id": call_id, "content": content})

    async def _invoke_tool(
        self,
        name: str,
        arguments: str,
        expected_tool_args: dict[str, Any] | None,
    ) -> str:
        """解析模型参数并执行已注册工具，结果统一序列化为 JSON 文本。"""
        try:
            parsed = json.loads(arguments or "{}")
            _validate_tool_args(parsed, expected_tool_args)
            result = await self._tools[name].ainvoke(parsed)
            content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            self.last_results[name] = content
            return content
        except Exception as exc:
            content = json.dumps({"error": f"工具执行失败：{exc}"}, ensure_ascii=False)
            self.last_results[name] = content
            return content

    def _get_completions_client(self) -> Any:
        """取得 chat.completions 接口，兼容 LangChain 两种客户端层级。"""
        client = getattr(self._llm, "async_client", None)
        if client is None:
            raise TypeError("当前 LLM 未提供 OpenAI 兼容 async_client")
        completions = getattr(getattr(client, "chat", None), "completions", None)
        if completions is not None:
            return completions
        if hasattr(client, "create"):
            return client
        raise TypeError("当前 LLM 客户端未提供 chat.completions.create")


def _serialize_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """将 LangChain 消息转换为可回传的 OpenAI 兼容消息。"""
    return [_serialize_message(message) for message in messages]


def _serialize_message(message: BaseMessage) -> dict[str, Any]:
    """转换单条消息并保留已存在的 reasoning_content 和工具字段。"""
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    if isinstance(message, AIMessage):
        payload: dict[str, Any] = {"role": "assistant", "content": message.content or None}
        reasoning = message.additional_kwargs.get("reasoning_content")
        if reasoning is not None:
            payload["reasoning_content"] = reasoning
        if message.tool_calls:
            payload["tool_calls"] = [_serialize_langchain_tool_call(call) for call in message.tool_calls]
        return payload
    raise TypeError(f"不支持的 LangChain 消息类型：{type(message).__name__}")


def _serialize_assistant_response(message: Any) -> dict[str, Any]:
    """保存模型原始 assistant 响应，尤其不能丢失 reasoning_content。"""
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": getattr(message, "content", None),
    }
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning is not None:
        payload["reasoning_content"] = reasoning
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = [_serialize_response_tool_call(call) for call in tool_calls]
    return payload


def _serialize_langchain_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    """将 LangChain 工具调用转换为 OpenAI 的函数调用结构。"""
    return {
        "id": call["id"],
        "type": "function",
        "function": {
            "name": call["name"],
            "arguments": json.dumps(call.get("args", {}), ensure_ascii=False),
        },
    }


def _serialize_response_tool_call(call: Any) -> dict[str, Any]:
    """将 OpenAI SDK 工具调用对象转换为可重复发送的字典。"""
    function = call.function
    return {
        "id": call.id,
        "type": getattr(call, "type", "function"),
        "function": {"name": function.name, "arguments": function.arguments},
    }


def _validate_tool_args(
    actual: Any,
    expected: dict[str, Any] | None,
) -> None:
    """校验模型参数与服务端已识别的查询对象一致，避免查询错材料。"""
    if not expected:
        return
    if not isinstance(actual, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError(f"工具参数 {key} 与当前用户问题不一致")


def _message_content(content: Any) -> str:
    """提取字符串或内容分片中的文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return "" if content is None else str(content)
