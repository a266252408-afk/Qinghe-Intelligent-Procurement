# SDD — 文件存储服务（storage_service）

> **依据**：system-design.md §2.2.11，tech-stack.md §4.4，CLAUDE.md §3
> **代码位置**：`backend/app/storage/local_storage.py`

---

## 1. 功能描述

提供文件上传/读取/删除能力，隔离业务代码与底层存储细节。
MVP 实现为本地文件系统（`LocalStorage`），通过抽象接口 `StorageInterface` 预留 OSS 替换点。
路径规范：`{UPLOAD_DIR}/{team_id}/{type}/{yyyy/mm}/{uuid}{ext}`
type 分类：`list`（采购清单）、`quote`（报价单）、`knowledge`（知识库文件）、`inquiry`（询价单）

---

## 2. 接口签名

```python
from abc import ABC, abstractmethod
from fastapi import UploadFile
from app.schemas.storage import StoredFile

class StorageInterface(ABC):

    @abstractmethod
    async def save(
        self,
        file: UploadFile,      # FastAPI 上传文件对象
        team_id: int,          # 团队 ID，用于隔离目录
        file_type: str,        # 类型：list / quote / knowledge / inquiry
    ) -> StoredFile:
        """保存文件，返回存储路径与元数据。"""

    @abstractmethod
    async def read(
        self,
        path: str,             # save() 返回的相对路径
    ) -> bytes:
        """按路径读取文件内容。"""

    @abstractmethod
    async def delete(
        self,
        path: str,             # save() 返回的相对路径
    ) -> None:
        """按路径删除文件。"""


class LocalStorage(StorageInterface):
    """MVP 本地文件系统实现。"""

    async def save(self, file: UploadFile, team_id: int, file_type: str) -> StoredFile: ...
    async def read(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> None: ...
```

### Pydantic 模型（`backend/app/schemas/storage.py`）

```python
class StoredFile(BaseModel):
    path: str          # 相对路径（数据库存储用）
    original_name: str # 原始文件名
    size_bytes: int    # 文件大小
    content_type: str  # MIME 类型
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `aiofiles` | 异步读写本地文件 |
| `aiofiles.os` | 异步创建目录、删除文件 |
| `app.core.config.settings` | 读取 `UPLOAD_DIR`、`MAX_FILE_SIZE_MB` |
| `app.core.exceptions` | 抛出业务异常 |

---

## 4. 异常处理

| 异常类 | 触发条件 | HTTP 状态码 |
|:------- |:-------- |:----------- |
| `FileTooLargeError` | 文件大小超过 `MAX_FILE_SIZE_MB`（默认 5MB） | 413 |
| `UnsupportedFormatError` | 文件扩展名不在白名单（xlsx/csv/txt/pdf/docx/md） | 415 |
| `FileNotFoundError`（自定义） | `read/delete` 时路径不存在 | 404 |

白名单按 `file_type` 区分：
- `list`：xlsx / csv / txt
- `quote`：xlsx / csv / txt
- `knowledge`：pdf / docx / xlsx / txt / md
- `inquiry`：xlsx
