"""应用配置。

所有敏感信息（API Key、SECRET_KEY）一律来自环境变量或 .env 文件，
代码与仓库中不包含任何真实密钥。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> backend/app -> backend -> 项目根目录
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# 优先读取项目根目录 .env，其次 backend/.env（不覆盖已存在的系统环境变量）
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)


def _clean(value: str | None) -> str:
    """读取环境变量时的清洗，防止「行内注释粘贴错」这类问题。

    常见错误写法：OCR_TIMEOUT=60#45、OCR_VISION_BASE_URL=https://api.deepseek.com#备用地址
    python-dotenv 只在「# 前面有空格」时把 # 当注释，所以这些值会连同 # 后面一起读进来，
    最终拼出 https://api.deepseek.com#https://... 这种非法地址并返回 404。
    这里统一在第一个 # 处截断，并去掉首尾空白与成对引号。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text[:1] in {"'", '"'} and text[-1:] == text[:1] and len(text) >= 2:
        text = text[1:-1].strip()
    if "#" in text:
        text = text.split("#", 1)[0].strip()
    return text


def _env(name: str, default: str = "") -> str:
    return _clean(os.getenv(name, default))


def _as_bool(value: str | None, default: bool = False) -> bool:
    text = _clean(value).lower()
    if not text:
        return default
    token = re.split(r"[\s,;]+", text)[0]
    return token in {"1", "true", "yes", "on", "y", "t"}


def _as_int(value: str | None, default: int) -> int:
    text = _clean(value)
    match = re.match(r"-?\d+", text)
    if not match:
        return default
    try:
        return int(match.group(0))
    except (TypeError, ValueError):
        return default


class Config:
    """基础配置，生产环境通过环境变量覆盖。"""

    # ---------- 基础 ----------
    APP_NAME = "智膳 AI"
    APP_SUBTITLE = "全场景健康膳食管家"
    APP_VERSION = _env("APP_VERSION", "1.0.0")
    ENV = _env("FLASK_ENV", "development")
    DEBUG = _as_bool(os.getenv("FLASK_DEBUG"), False)
    SECRET_KEY = _env("SECRET_KEY", "dev-only-secret-change-me-in-production")

    # ---------- 数据库 ----------
    DATA_DIR = Path(_env("DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
    DEFAULT_SQLITE = f"sqlite:///{(DATA_DIR / 'food_safety.db').as_posix()}"
    SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL", DEFAULT_SQLITE)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ---------- 文件上传 ----------
    UPLOAD_DIR = Path(_env("UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))).resolve()
    MAX_CONTENT_LENGTH_MB = _as_int(os.getenv("MAX_CONTENT_LENGTH_MB"), 20)
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH_MB * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
    # 上传图片的最长边，超过则等比压缩（手机原图往往 4000px 以上）
    IMAGE_MAX_EDGE = _as_int(os.getenv("IMAGE_MAX_EDGE"), 2200)

    # ---------- CORS ----------
    CORS_ORIGINS = [
        origin.strip()
        for origin in _env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:4173,http://127.0.0.1:4173,"
            "http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    ]

    # ---------- 账号 / 会话 ----------
    SESSION_DAYS = _as_int(os.getenv("SESSION_DAYS"), 30)
    # 登录验证码（默认开启；测试环境关闭，另用开关测试）
    LOGIN_CAPTCHA = _as_bool(os.getenv("LOGIN_CAPTCHA"), True)
    CAPTCHA_TTL_SECONDS = _as_int(os.getenv("CAPTCHA_TTL_SECONDS"), 300)
    CAPTCHA_ECHO = _as_bool(os.getenv("CAPTCHA_ECHO"), False)
    # 公共演示模式：true 时未登录用户只能看到演示数据（不允许写入）
    DEMO_MODE = _as_bool(os.getenv("DEMO_MODE"), False)
    SEED_DEMO_ACCOUNT = _as_bool(os.getenv("SEED_DEMO_ACCOUNT"), True)
    DEMO_USERNAME = _env("DEMO_USERNAME", "demo")
    DEMO_PASSWORD = _env("DEMO_PASSWORD", "demo123456")

    # ---------- OCR ----------
    # auto: 有本地 OCR 引擎用本地；否则有视觉模型用视觉模型；再否则 demo
    OCR_PROVIDER = _env("OCR_PROVIDER", "auto").lower()
    OCR_TIMEOUT = _as_int(os.getenv("OCR_TIMEOUT"), 45)
    OCR_LANG = _env("OCR_LANG", "ch")
    # OpenAI 兼容的视觉模型（如 deepseek-flash / qwen-vl-max / glm-4v-plus / gpt-4o-mini）
    # 只填到站点根或 /v1，不要带 /chat/completions
    OCR_VISION_BASE_URL = _env("OCR_VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    OCR_VISION_API_KEY = _env("OCR_VISION_API_KEY", "")
    OCR_VISION_MODEL = _env("OCR_VISION_MODEL", "qwen-vl-max")

    # ---------- 大语言模型 ----------
    # auto: 有 Key 用 LLM；否则使用基础规则模式（会被明确标注）
    AI_PROVIDER = _env("AI_PROVIDER", "auto").lower()
    AI_BASE_URL = _env("AI_BASE_URL", "https://api.deepseek.com/v1")
    AI_API_KEY = _env("AI_API_KEY", "")
    AI_MODEL = _env("AI_MODEL", "deepseek-chat")
    # 家庭食材管家食谱 Agent：auto（有 Key 用大模型，失败降级）/ ai / rule
    RECIPE_AGENT_MODE = _env("RECIPE_AGENT_MODE", "auto").strip().lower()
    # 食材智能录入：auto（有 Key 用大模型解析）/ rule（只走规则）
    PANTRY_IMPORT_MODE = _env("PANTRY_IMPORT_MODE", "auto").strip().lower()
    # 可选联网检索（Tavily）；未配置时使用内置保质期常识表
    TAVILY_API_KEY = _env("TAVILY_API_KEY", "")
    # 可选条码商品库，URL 中用 {barcode} 占位；未配置时明确返回「未接入」
    # 商业条码库：showapi（万维易源 66-22）/ generic（自建代理）/ none
    BARCODE_PROVIDER = _env("BARCODE_PROVIDER", "auto").strip().lower()
    SHOWAPI_APP_KEY = _env("SHOWAPI_APP_KEY", "")
    BARCODE_API_URL = _env("BARCODE_API_URL", "")
    BARCODE_API_KEY = _env("BARCODE_API_KEY", "")
    BARCODE_API_KEY_HEADER = _env("BARCODE_API_KEY_HEADER", "X-API-Key")
    # 每日 8 点通知：SMTP 未配置时写模拟邮件日志
    SMTP_HOST = _env("SMTP_HOST", "")
    SMTP_PORT = _as_int(os.getenv("SMTP_PORT"), 587)
    SMTP_USER = _env("SMTP_USER", "")
    SMTP_PASSWORD = _env("SMTP_PASSWORD", "")
    SMTP_FROM = _env("SMTP_FROM", "")
    SMTP_STARTTLS = _as_bool(os.getenv("SMTP_STARTTLS"), True)
    PANTRY_NOTIFY_EMAIL_TO = _env("PANTRY_NOTIFY_EMAIL_TO", "")
    WECOM_WEBHOOK_URL = _env("WECOM_WEBHOOK_URL", "")
    DINGTALK_WEBHOOK_URL = _env("DINGTALK_WEBHOOK_URL", "")
    PANTRY_NOTIFY_LOG_DIR = _env("PANTRY_NOTIFY_LOG_DIR", "")
    AI_TIMEOUT = _as_int(os.getenv("AI_TIMEOUT"), 50)
    AI_TEMPERATURE = float(_clean(os.getenv("AI_TEMPERATURE", "0.2")) or 0.2)

    # ---------- 食安科普助手（RAG） ----------
    # retrieval：只做检索直答（答案逐字来自知识库，不调用大模型）
    # ai       ：在检索结果内用大模型改写，并做引用白名单 + 逐句依据校验
    # auto     ：配置了 AI_API_KEY 就用 ai，否则 retrieval
    ASSISTANT_MODE = _env("ASSISTANT_MODE", "auto").lower()
    # 知识库未直接命中时，是否允许大模型在「相近条目」范围内判断（默认允许）
    ASSISTANT_AI_FALLBACK = _env("ASSISTANT_AI_FALLBACK", "1")
    # 科普助手专用大模型接口（留空则复用上面的 AI_* 配置）
    ASSISTANT_LLM_BASE_URL = _env("ASSISTANT_LLM_BASE_URL", "")
    ASSISTANT_LLM_API_KEY = _env("ASSISTANT_LLM_API_KEY", "")
    ASSISTANT_LLM_MODEL = _env("ASSISTANT_LLM_MODEL", "")
    ASSISTANT_LLM_TIMEOUT = _as_int(os.getenv("ASSISTANT_LLM_TIMEOUT"), 0)  # 0 表示复用 AI_TIMEOUT
    ASSISTANT_LLM_TEMPERATURE = float(_clean(os.getenv("ASSISTANT_LLM_TEMPERATURE", "0")) or 0)

    # =====================================================================
    # 统一大模型配置：家庭食材管家食谱、AI 食材解析、配料解读、健康提示、
    # 存储建议、AI 科普助手全部复用同一套 DeepSeek Key / Base / Model。
    # 科普助手配置为主；未配置时自动回退到 AI_* / OCR_VISION_*。
    # 这样只需要在 .env 维护一个 ASSISTANT_LLM_API_KEY。
    # =====================================================================
    _assistant_key = ASSISTANT_LLM_API_KEY or AI_API_KEY or OCR_VISION_API_KEY
    _assistant_base = ASSISTANT_LLM_BASE_URL or AI_BASE_URL or OCR_VISION_BASE_URL
    _assistant_model = ASSISTANT_LLM_MODEL or AI_MODEL or OCR_VISION_MODEL
    if _assistant_key:
        AI_API_KEY = _assistant_key
        AI_BASE_URL = _assistant_base
        AI_MODEL = _assistant_model
        if not ASSISTANT_LLM_TIMEOUT:
            ASSISTANT_LLM_TIMEOUT = AI_TIMEOUT
    if not ASSISTANT_LLM_API_KEY:
        ASSISTANT_LLM_API_KEY = AI_API_KEY
        ASSISTANT_LLM_BASE_URL = ASSISTANT_LLM_BASE_URL or AI_BASE_URL
        ASSISTANT_LLM_MODEL = ASSISTANT_LLM_MODEL or AI_MODEL
    # 视觉 OCR 也复用同一把 Key；模型/Base 仍独立，避免把纯文本模型用于视觉识别
    if not OCR_VISION_API_KEY:
        OCR_VISION_API_KEY = _assistant_key
    # 知识库与相近条目都无法回答时，是否允许一声明式「通用大模型回答」
    ASSISTANT_GENERAL_ANSWER = _env("ASSISTANT_GENERAL_ANSWER", "1")

    # ---------- 生产部署 ----------
    # 由 Flask 直接托管前端构建产物（单服务部署，避免跨域配置）
    SERVE_FRONTEND = _as_bool(os.getenv("SERVE_FRONTEND"), False)
    FRONTEND_DIST = _env("FRONTEND_DIST", str(PROJECT_ROOT / "frontend" / "dist"))

    # ---------- 业务 ----------
    RULESET_VERSION = _env("RULESET_VERSION", "2025.11")
    PAGE_SIZE = _as_int(os.getenv("PAGE_SIZE"), 8)
    MAX_PAGE_SIZE = _as_int(os.getenv("MAX_PAGE_SIZE"), 50)
    LOG_LEVEL = _env("LOG_LEVEL", "INFO")

    # 前端（用于文档与二维码提示，不参与鉴权）
    PUBLIC_SITE_URL = _env("PUBLIC_SITE_URL", "")

    @classmethod
    def init_dirs(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class TestConfig(Config):
    """pytest 使用：独立临时数据库 + 临时上传目录 + 强制演示/规则模式。"""

    TESTING = True
    ENV = "testing"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{(Path(__import__('tempfile').gettempdir()) / 'food_safety_test.db').as_posix()}"
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    UPLOAD_DIR = Path(__import__("tempfile").gettempdir()) / "food_safety_test_uploads"
    OCR_PROVIDER = "demo"
    AI_PROVIDER = "rule"
    # 测试环境不读取真实 Key，避免误调外部 API
    AI_API_KEY = ""
    PANTRY_IMPORT_MODE = "rule"
    RECIPE_AGENT_MODE = "rule"
    OCR_VISION_API_KEY = ""
    ASSISTANT_LLM_API_KEY = ""
    ASSISTANT_LLM_BASE_URL = ""
    ASSISTANT_LLM_MODEL = ""
    ASSISTANT_GENERAL_ANSWER = "1"
    ASSISTANT_MODE = "retrieval"
    SEED_DEMO_ACCOUNT = False
    LOGIN_CAPTCHA = "0"
    CAPTCHA_ECHO = "1"
    SECRET_KEY = "test-secret"
    MAX_CONTENT_LENGTH_MB = 10
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
