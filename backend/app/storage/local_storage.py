"""本地文件系统存储服务
依据：docs/module-sdd/storage_service.md
"""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import aiofiles.os
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import FileTooLargeError, FileNotFoundAppError, UnsupportedFormatError
from app.schemas.storage import StoredFile

# 各 file_type 的允许扩展名白名单
_ALLOWED_EXTS: dict[str, set[str]] = {
    "list":      {".xlsx", ".csv", ".txt"},
    "quote":     {".xlsx", ".csv", ".txt"},
    "knowledge": {".xlsx", ".txt", ".md", ".pdf"},
    "inquiry":   {".xlsx"},
}


class StorageInterface(ABC):
    """文件存储抽象接口（开闭原则，MVP→OSS 只替换实现）"""

    @abstractmethod
    async def save(self, file: UploadFile, team_id: int, file_type: str) -> StoredFile: ...

    @abstractmethod
    async def read(self, path: str) -> bytes: ...

    @abstractmethod
    async def delete(self, path: str) -> None: ...


class LocalStorage(StorageInterface):
    """MVP 本地文件系统实现
    路径规范：{UPLOAD_DIR}/{team_id}/{type}/{yyyy/mm}/{uuid}{ext}
    """

    def __init__(self) -> None:
        self._root = Path(settings.UPLOAD_DIR)
        self._max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    async def save(self, file: UploadFile, team_id: int, file_type: str) -> StoredFile:
        """保存上传文件，返回 StoredFile 元数据

        分块流式写入并边写边校验大小，避免大文件全量读入内存
        （高并发上传时内存峰值可控），超限时立即删除半成品。
        """
        suffix = Path(file.filename or "").suffix.lower()
        allowed = _ALLOWED_EXTS.get(file_type, set())
        if suffix not in allowed:
            raise UnsupportedFormatError(
                f"文件类型 {suffix} 不支持，{file_type} 允许：{', '.join(sorted(allowed))}"
            )

        now = datetime.now(timezone.utc)
        rel_dir = Path(str(team_id)) / file_type / now.strftime("%Y/%m")
        abs_dir = self._root / rel_dir
        await aiofiles.os.makedirs(abs_dir, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{suffix}"
        abs_path = abs_dir / filename
        size_bytes = 0
        try:
            async with aiofiles.open(abs_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):  # 1MB 分块
                    size_bytes += len(chunk)
                    if size_bytes > self._max_bytes:
                        raise FileTooLargeError()
                    await f.write(chunk)
        except Exception:
            await aiofiles.os.remove(abs_path)
            raise

        return StoredFile(
            path=str(rel_dir / filename),
            original_name=file.filename or filename,
            size_bytes=size_bytes,
            content_type=file.content_type or "application/octet-stream",
        )

    async def read(self, path: str) -> bytes:
        """读取文件内容"""
        abs_path = self._root / path
        if not abs_path.exists():
            raise FileNotFoundAppError(f"文件不存在：{path}")
        async with aiofiles.open(abs_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> None:
        """删除文件"""
        abs_path = self._root / path
        if not abs_path.exists():
            raise FileNotFoundAppError(f"文件不存在：{path}")
        await aiofiles.os.remove(abs_path)


# 模块级单例，供依赖注入使用
local_storage = LocalStorage()
