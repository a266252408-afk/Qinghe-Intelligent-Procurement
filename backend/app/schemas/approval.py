"""审批相关 Pydantic Schema"""
from datetime import datetime
from pydantic import BaseModel



class ApprovalAction(BaseModel):
    reason: str | None = None     # 通过时可为 None；驳回时必填


class ApprovalOut(BaseModel):
    """单次审批记录输出"""
    record_id: int
    order_id: int
    approver_id: int
    decision: str                  # "approved" / "rejected"
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# 兼容旧别名
ApprovalRecordOut = ApprovalOut


class PendingOrderOut(BaseModel):
    """待审批采购单摘要"""
    order_id: int
    project_id: int
    project_name: str
    name: str | None = None
    creator_id: int
    creator_name: str
    total_amount: float | None
    remark: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PendingListOut(BaseModel):
    total: int
    items: list[PendingOrderOut]


class ApprovalListOut(BaseModel):
    total: int
    items: list[PendingOrderOut]  # 返回审批页所需的采购单摘要
