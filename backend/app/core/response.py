"""统一 API 响应格式：{"code": 0, "msg": "ok", "data": {...}}"""
from typing import Any
from pydantic import BaseModel


class APIResponse(BaseModel):
    """所有 API 返回此格式（CLAUDE.md §7 红线）"""
    code: int = 0
    msg: str = "ok"
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None, msg: str = "ok") -> "APIResponse":
        """构造成功响应"""
        return cls(code=0, msg=msg, data=data)

    @classmethod
    def error(cls, code: int, msg: str) -> "APIResponse":
        """构造失败响应"""
        return cls(code=code, msg=msg, data=None)
