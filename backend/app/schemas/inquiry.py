"""询价单 Agent Pydantic Schema"""
from pydantic import BaseModel


class InquiryGenerateInput(BaseModel):
    order_id: int
    template_id: str               # standard / simple / with_delivery / greening_boq


class TemplateInfo(BaseModel):
    template_id: str
    name: str
    description: str


class InquiryResult(BaseModel):
    inquiry_id: int
    file_path: str
    filename: str
    preview_items: list[dict] = []
    template_id: str
    template_name: str
    download_url: str
