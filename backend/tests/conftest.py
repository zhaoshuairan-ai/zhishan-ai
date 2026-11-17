"""pytest 公共夹具。

运行方式（在 backend 目录下）：
    .venv\\Scripts\\python.exe -m pytest -v
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisRecord,
    AuditLog,
    CheckRule,
    Feedback,
    RecordNote,
    RuleRevision,
    ServiceEvent,
    AuthSession,
    ChatMessage,
    ChatSession,
    IngredientAnalysis,
    KnowledgeEntry,
    LabelCheck,
    NutritionFact,
    OcrResult,
    PantryItem,
    BarcodeCache,
    CookLog,
    HealthProfile,
    RecipePlan,
    ReportMeta,
    UploadedImage,
    User,
)
from app.seed.knowledge_seed import KNOWLEDGE_ENTRIES  # noqa: E402
from app.services import assistant_service, knowledge_service  # noqa: E402

USER_TABLES = [
    CookLog,
    BarcodeCache,
    RecipePlan,
    PantryItem,
    BarcodeCache,
    CookLog,
    HealthProfile,
    ServiceEvent,
    RuleRevision,
    CheckRule,
    RecordNote,
    Feedback,
    AuditLog,
    ChatMessage,
    ChatSession,
    ReportMeta,
    LabelCheck,
    NutritionFact,
    IngredientAnalysis,
    OcrResult,
    UploadedImage,
    AnalysisRecord,
    AuthSession,
    User,
]

SAMPLE_LABEL_LINES = [
    "测试牌 原味饼干（接口测试）",
    "净含量：150g",
    "配料：小麦粉、植物油、白砂糖、食用盐、碳酸氢钠、酵母",
    "营养成分表（每100g）",
    "能量 1900kJ 23%   蛋白质 8.2g 14%",
    "脂肪 17.5g 29%    碳水化合物 66.1g 22%",
    "钠 420mg 21%",
    "生产日期：2026-02-10    保质期：12个月",
    "贮存条件：置于阴凉干燥处",
    "生产者：测试食品有限公司",
    "产品标准号：GB/T 20980",
    "致敏物质提示：含有小麦",
]


def make_label_png(lines: list[str] | None = None) -> bytes:
    lines = lines or SAMPLE_LABEL_LINES
    font_path = None
    for candidate in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).exists():
            font_path = candidate
            break
    font = ImageFont.truetype(font_path, 26) if font_path else ImageFont.load_default()
    image = Image.new("RGB", (900, 90 + 44 * len(lines)), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    y = 30
    for line in lines:
        draw.text((26, y), line, fill=(20, 20, 20), font=font)
        y += 44
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        knowledge_service.upsert_seed(KNOWLEDGE_ENTRIES)
        assistant_service.upsert_entries()
        from app.services.admin_service import seed_rules

        seed_rules()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def clean_database(app):
    """每个测试前清空用户数据（保留知识库），保证测试互不影响。"""
    with app.app_context():
        for model in USER_TABLES:
            db.session.execute(delete(model))
        db.session.commit()
        from app.services.admin_service import seed_rules

        seed_rules()
        upload_dir = Path(app.config["UPLOAD_DIR"])
        if upload_dir.exists():
            for path in upload_dir.glob("*"):
                if path.is_file():
                    path.unlink()
    yield


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def image_bytes() -> bytes:
    return make_label_png()


def register_user(client, username: str = "tester", password: str = "Test123456") -> str:
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["token"]


@pytest.fixture()
def token(client) -> str:
    return register_user(client, username="tester")


@pytest.fixture()
def auth(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_auth(client) -> dict:
    token = register_user(client, username="other_user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def record_factory(client, auth, image_bytes):
    """上传图片并返回记录信息；可选执行 OCR 与分析。"""

    def _create(*, run_ocr: bool = False, analyze: bool = False):
        resp = client.post(
            "/api/upload",
            headers=auth,
            data={"file": (io.BytesIO(image_bytes), "label.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, resp.get_json()
        record_id = resp.get_json()["data"]["record"]["id"]
        if run_ocr:
            ocr_resp = client.post("/api/ocr", headers=auth, json={"record_id": record_id})
            assert ocr_resp.status_code == 200, ocr_resp.get_json()
        if analyze:
            analyze_resp = client.post("/api/analyze", headers=auth, json={"record_id": record_id})
            assert analyze_resp.status_code == 200, analyze_resp.get_json()
        return record_id

    return _create


@pytest.fixture()
def analyzed_record(record_factory) -> int:
    return record_factory(run_ocr=True, analyze=True)


@pytest.fixture()
def admin_token(app, client):
    """创建一个测试管理员并返回其会话令牌（不经由公开注册接口）。"""
    from app.services.admin_service import create_admin
    from app.utils.security import issue_session

    with app.app_context():
        user, _ = create_admin("admin_tester", "AdminTest12345")
        token, _ = issue_session(user)
    return token


@pytest.fixture()
def admin_auth(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
