"""对话 Agent Pydantic Schema"""
from pydantic import BaseModel, Field, model_validator

from app.schemas.router import RouteIntent


class ChatInput(BaseModel):
    message: str
    session_id: int
    file_id: str | None = None
    file_type: str | None = None
    file_name: str | None = None
    upload_id: int | None = None
    # 人工确认续跑：pending_token 必须与 forced_intent 同时出现
    forced_intent: RouteIntent | None = None
    pending_token: str | None = None
    route_cancelled: bool = False

    @model_validator(mode="after")
    def _validate_pending_choice(self) -> "ChatInput":
        if self.pending_token and not self.forced_intent:
            raise ValueError("提交待确认路由时必须指定 forced_intent")
        if self.route_cancelled and self.forced_intent != "chat":
            raise ValueError("取消待确认路由时 forced_intent 必须为 chat")
        if self.route_cancelled and not self.pending_token:
            raise ValueError("route_cancelled 只能用于待确认路由续跑")
        return self


class ChatChunk(BaseModel):
    delta: str
    done: bool = False
    session_id: int
    type: str | None = None
    data: dict | None = None


class MaterialHistoryToolInput(BaseModel):
    """长期材料查询工具的参数，由模型按 schema 自主填写。

    服务端只做格式校验，不做正则预提取；团队隔离的 team_id 由工具闭包绑定，
    不属于工具参数。四项条件至少一项非空，避免无条件全表查询。
    """

    material_name: str | None = Field(
        default=None,
        max_length=100,
        description="要查询历史报价或成交价的材料名称，例如：银杏、香樟；按供应商或日期查询时可留空",
    )
    supplier_name: str | None = Field(
        default=None,
        max_length=100,
        description="供应商名称关键词，可选",
    )
    date_from: str | None = Field(
        default=None,
        max_length=10,
        description="报价日期起点，格式 YYYY-MM-DD，可选",
    )
    date_to: str | None = Field(
        default=None,
        max_length=10,
        description="报价日期终点，格式 YYYY-MM-DD，可选",
    )

    @model_validator(mode="after")
    def _require_any_condition(self) -> "MaterialHistoryToolInput":
        """至少提供一个筛选条件，防止模型传空参数导致全量拉取。"""
        conditions = (self.material_name, self.supplier_name, self.date_from, self.date_to)
        if not any(value and str(value).strip() for value in conditions):
            raise ValueError("至少提供材料名称、供应商、日期起点或日期终点之一")
        return self
