"""JEV 客户端协议与错误映射测试（不联网）。"""
import json

import httpx
import pytest

from app.core.exceptions import ConfigError, LLMUnavailableError
from app.services.jev_client import JevClient

pytestmark = pytest.mark.asyncio


def _client(handler, timeout_s: float = 1.0) -> JevClient:
    return JevClient(
        api_key="test-key",
        endpoint="https://jev.example/v1/systemone",
        model="@makers/jev",
        timeout_s=timeout_s,
        transport=httpx.MockTransport(handler),
    )


async def test_judge_sends_systemone_request_and_returns_payload():
    """请求体只包含 model/state/questions，鉴权走 Bearer。"""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "jev-1.13.0",
            "answers": {"intent": {"type": "choice", "choice": "compare",
                                   "confidence": 0.9, "probabilities": {"compare": 0.9}}},
            "usage": {"input_tokens": 10, "output_tokens": 2},
        })

    payload = await _client(handler).judge(
        {"user_message": "比价"}, {"intent": {"type": "choice", "instructions": "x",
                                           "criteria": {"compare": "比价"}}}
    )

    assert captured["url"] == "https://jev.example/v1/systemone"
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "@makers/jev"
    assert payload["answers"]["intent"]["choice"] == "compare"


@pytest.mark.parametrize("status", [400, 401, 422])
async def test_config_errors_are_not_retryable(status):
    """Key/请求体错误映射为 ConfigError，交由调用方降级。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="bad request")

    with pytest.raises(ConfigError):
        await _client(handler).judge({}, {})


@pytest.mark.parametrize("status", [429, 500, 503, 529])
async def test_upstream_errors_map_to_unavailable(status):
    """限流/5xx 映射为 LLMUnavailableError。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="upstream busy")

    with pytest.raises(LLMUnavailableError):
        await _client(handler).judge({}, {})


async def test_network_error_maps_to_unavailable():
    """连接失败不泄露底层异常类型给上层。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(LLMUnavailableError):
        await _client(handler).judge({}, {})


async def test_non_json_or_missing_answers_is_unavailable():
    """协议异常统一按不可用处理，触发规则降级。"""
    def non_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>oops</html>")

    def no_answers(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "jev-1.13.0"})

    with pytest.raises(LLMUnavailableError):
        await _client(non_json).judge({}, {})
    with pytest.raises(LLMUnavailableError):
        await _client(no_answers).judge({}, {})
