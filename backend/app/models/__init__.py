"""app/models/__init__.py — 统一导入所有模型，供 alembic autogenerate 发现"""
from app.models.user import User, Team, TeamMember, TeamInvitation  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.order import PurchaseOrder, PurchaseItem  # noqa: F401
from app.models.quote import Quote, QuoteItem, InquirySheet  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.approval import ApprovalRecord  # noqa: F401
from app.models.knowledge import IndustryKnowledge, ConversationSession, Message  # noqa: F401
from app.models.material_history import MaterialHistoryRecord, QuoteUpload  # noqa: F401
from app.models.supplier_order import SupplierOrder, SupplierOrderItem  # noqa: F401
from app.models.receipt import Receipt, ReceiptItem  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.llm_log import LLMCallLog, LLMCache  # noqa: F401
