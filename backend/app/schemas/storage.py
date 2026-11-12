"""文件存储 Pydantic Schema"""
from pydantic import BaseModel


class StoredFile(BaseModel):
    path: str              # 相对路径（数据库存储）
    original_name: str
    size_bytes: int
    content_type: str
