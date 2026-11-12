"""JEV（TypeSafe System One）客户端 — 强类型判定模型，非 OpenAI 兼容协议。

JEV 只接受 POST /v1/systemone，返回 choice/score/noul 的概率与置信度，
不支持流式与 /v1/chat/completions。本模块只负责传输与错误映射，
路由规则、问题构造与降级策略由 RouterAgent 负责。
"""
import logging

import httpx

from app.core.exceptions import ConfigError, LLMUnavailableError

logger = logging.getLogger(__name__)

# 这些状态码属于配置/请求问题，重试无意义
_CONFIG_ERROR_CODES = {400, 401, 403, 404, 422}
# 这些状态码属于上游瞬时故障，交由调用方降级
_TRANSIENT_ERROR_CODES = {408, 429, 500, 502, 503, 504, 529}


class JevClient:
    """TypeSafe System One 协议客户端。"""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._model = model
        self._timeout_s = timeout_s
        self._transport = transport

    async def judge(self, state: dict, questions: dict) -> dict:
        """提交一次并行判定请求，返回原始 JSON。

        state 与 questions 的结构由调用方构造；question id 不会发送给模型，
        因此判定规则必须写在每个问题的 instructions 中。
        """
        payload = {"model": self._model, "state": state, "questions": questions}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(self._endpoint, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise LLMUnavailableError(f"JEV 连接失败：{exc}") from exc

        if response.status_code in _CONFIG_ERROR_CODES:
            raise ConfigError(
                f"JEV 配置或请求错误 HTTP {response.status_code}：{self._body_excerpt(response)}"
            )
        if response.status_code in _TRANSIENT_ERROR_CODES:
            raise LLMUnavailableError(
                f"JEV 上游暂不可用 HTTP {response.status_code}：{self._body_excerpt(response)}"
            )
        if response.status_code >= 400:
            raise LLMUnavailableError(
                f"JEV 未知错误 HTTP {response.status_code}：{self._body_excerpt(response)}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMUnavailableError("JEV 返回了非 JSON 响应") from exc
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise LLMUnavailableError("JEV 响应缺少 answers 字段")
        return data

    @staticmethod
    def _body_excerpt(response: httpx.Response) -> str:
        """截断错误响应体，避免日志被超长内容淹没。"""
        try:
            return response.text[:500]
        except Exception:  # pragma: no cover - 极端编码异常
            return "<unreadable body>"
