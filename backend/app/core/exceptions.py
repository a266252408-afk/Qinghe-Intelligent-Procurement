"""自定义异常类，统一在此定义，API 层捕获转 HTTP 响应"""
from fastapi import HTTPException, status


class AppError(Exception):
    """业务异常基类"""
    status_code: int = 500
    message: str = "内部错误"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.message
        super().__init__(self.message)

    def to_http(self) -> HTTPException:
        return HTTPException(status_code=self.status_code, detail=self.message)


# ── 认证相关 ─────────────────────────────────────────────────────────────

class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "用户名或密码错误"


class UsernameAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    message = "用户名已存在"


class TokenExpiredError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Token 已过期，请重新登录"


class InvalidTokenError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "无效的 Token"


class InvalidInviteCodeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "邀请码无效或已失效"


class AlreadyInTeamError(AppError):
    status_code = status.HTTP_409_CONFLICT
    message = "用户已加入团队"


class CannotLeaveTeamError(AppError):
    status_code = status.HTTP_409_CONFLICT
    message = "当前团队没有可接管的管理员，暂时不能退出团队"


class TeamNameRequiredError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "管理员注册必须填写团队名称"


class UserNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "被邀请用户不存在"


class InvitationNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "邀请不存在或已处理"


class InvitationAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    message = "该用户已有待处理邀请"


# ── 权限相关 ─────────────────────────────────────────────────────────────

class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    message = "权限不足"


# ── 资源不存在 ────────────────────────────────────────────────────────────

class ProjectNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "项目不存在"


class DuplicateProjectNameError(AppError):
    status_code = status.HTTP_409_CONFLICT
    message = "当前团队已存在同名项目"


class OrderNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "采购单不存在"


class QuoteNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "报价不存在"


class SessionNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "会话不存在"


class FileNotFoundAppError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "文件不存在"


class QuoteUploadNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "报价上传记录不存在或不属于当前团队"


class TemplateNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "模板不存在"


# ── 业务逻辑 ─────────────────────────────────────────────────────────────

class InvalidStatusTransitionError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "不允许的状态转换"


class EmptyOrderError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "采购单无采购项，不可操作"


class MissingSupplierSelectionError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "请为每项材料选择供应商并填写成交价"


class MissingRejectReasonError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "驳回时必须填写原因"


class NoQuoteError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "该采购单暂无报价，请先上传报价文件"


class WeightSumError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "比价权重之和必须等于 1.0"


# ── 文件存储 ─────────────────────────────────────────────────────────────

class FileTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    message = "文件过大，请压缩或拆分后上传（最大 5MB）"


class UnsupportedFormatError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    message = "不支持的文件格式"


# ── 大模型相关 ────────────────────────────────────────────────────────────

class LLMUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "AI 服务暂时不可用，请稍后再试"


class ParseError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "文件解析失败，请检查文件格式"


class ConfigError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = "服务配置错误，请联系管理员"


# ── 路由人工确认 ──────────────────────────────────────────────────────────

class RouteDecisionNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    message = "待确认的路由选择不存在"


class RouteDecisionExpiredError(AppError):
    status_code = status.HTTP_410_GONE
    message = "该路由选择已过期，请重新发送消息"


class RouteDecisionResolvedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    message = "该路由选择已处理"


# ── 知识库 ────────────────────────────────────────────────────────────────

class KnowledgeDocError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "知识库文件处理失败"


class UnsupportedChatFileError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    message = "对话附件格式不支持"
