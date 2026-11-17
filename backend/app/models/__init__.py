"""ORM 模型汇总导入（确保 db.create_all() 能发现全部表）。"""
from .admin import (
    AUDIT_ACTIONS,
    AUDIT_RESULTS,
    FEEDBACK_STATUS,
    RULE_ACTIONS,
    AuditLog,
    CheckRule,
    Feedback,
    RecordNote,
    RuleRevision,
    ServiceEvent,
)
from .assistant import ASSISTANT_CATEGORIES, SOURCE_KINDS, AssistantEntry, ChatMessage, ChatSession
from .check import OVERALL_LABELS, LabelCheck
from .favorite import UserFavoriteRecipe
from .family import Family
from .ingredient import MODE_LABELS, IngredientAnalysis
from .knowledge import CATEGORIES, SOURCE_TYPES, VERIFICATION, KnowledgeEntry
from .nutrition import NutritionFact
from .pantry import (
    HEALTH_CONDITIONS,
    HEALTH_GOALS,
    PANTRY_CATEGORIES,
    BarcodeCache,
    CookLog,
    HealthProfile,
    PantryItem,
    RecipePlan,
)
from .ocr import OCR_FIELDS, OcrResult
from .prompt import PromptTemplate
from .record import STATUS_LABELS, AnalysisRecord
from .report import ReportMeta
from .upload import UploadedImage
from .user import AuthSession, User, utcnow

__all__ = [
    "User",
    "AuthSession",
    "AuditLog",
    "CheckRule",
    "RuleRevision",
    "RecordNote",
    "Feedback",
    "ServiceEvent",
    "AUDIT_ACTIONS",
    "AUDIT_RESULTS",
    "RULE_ACTIONS",
    "FEEDBACK_STATUS",
    "AnalysisRecord",
    "UserFavoriteRecipe",
    "Family",
    "UploadedImage",
    "OcrResult",
    "IngredientAnalysis",
    "NutritionFact",
    "LabelCheck",
    "KnowledgeEntry",
    "PantryItem",
    "BarcodeCache",
    "CookLog",
    "HealthProfile",
    "RecipePlan",
    "PANTRY_CATEGORIES",
    "HEALTH_CONDITIONS",
    "HEALTH_GOALS",
    "ReportMeta",
    "PromptTemplate",
    "AssistantEntry",
    "ChatSession",
    "ChatMessage",
    "ASSISTANT_CATEGORIES",
    "SOURCE_KINDS",
    "OCR_FIELDS",
    "STATUS_LABELS",
    "MODE_LABELS",
    "OVERALL_LABELS",
    "CATEGORIES",
    "SOURCE_TYPES",
    "VERIFICATION",
    "utcnow",
]
