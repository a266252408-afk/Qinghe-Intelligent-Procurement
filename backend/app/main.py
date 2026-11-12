"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.response import APIResponse
from app.db.session import init_db

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库；关闭时清理资源"""
    logger.info("启动：初始化数据库")
    await init_db()
    yield
    logger.info("关闭：清理完成")


app = FastAPI(
    title="园林工程智能采购助手",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# CORS — 开发环境允许所有来源，生产环境收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 全局异常处理 ─────────────────────────────────────────────────────────

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """将业务异常转换为统一响应格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse.error(exc.status_code, exc.message).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """将请求参数校验错误转换为统一响应格式"""
    return JSONResponse(
        status_code=422,
        content=APIResponse.error(422, "请求参数校验失败").model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """将 FastAPI HTTP 异常转换为统一响应格式"""
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse.error(exc.status_code, detail).model_dump(),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常兜底处理"""
    logger.exception("未处理异常", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=APIResponse.error(500, "服务内部错误").model_dump(),
    )


# ── 路由注册 ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> APIResponse:
    """健康检查"""
    return APIResponse.ok({"status": "ok"})


from app.api import auth, projects, orders, approvals, knowledge, chat, quotes, receipts  # noqa: E402

app.include_router(auth.router,      prefix="/api/auth",      tags=["认证"])
app.include_router(projects.router,  prefix="/api/projects",  tags=["项目"])
app.include_router(orders.router,    prefix="/api/orders",    tags=["采购单"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["审批"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库"])
app.include_router(chat.router,      prefix="/api/chat",      tags=["对话"])
app.include_router(quotes.router,    prefix="/api/quotes",    tags=["报价单"])
app.include_router(receipts.router,  prefix="/api/receipts",  tags=["收货管理"])
