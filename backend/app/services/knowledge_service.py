"""知识库检索服务：关键词搜索、配料匹配、AI 上下文组织。"""
from __future__ import annotations

import hashlib
import logging
import re
import threading

from flask import current_app

from sqlalchemy import func, or_

from ..extensions import db
from ..models.knowledge import CATEGORIES, KnowledgeEntry
from ..utils.validators import clean_text, natural_key

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    text = natural_key(text or "")
    return re.sub(r"[\s()（）\[\]【】,，、;；:：。./\\-]", "", text)


def upsert_seed(entries: list[dict]) -> dict:
    """把种子条目幂等写入数据库（按 slug 更新），便于未来导入权威资料。"""
    created = 0
    updated = 0
    for payload in entries:
        entry = KnowledgeEntry.query.filter_by(slug=payload["slug"]).first()
        if entry is None:
            entry = KnowledgeEntry(slug=payload["slug"], title=payload["title"], category=payload["category"])
            db.session.add(entry)
            created += 1
        else:
            updated += 1
        for field in (
            "title",
            "aliases",
            "keywords",
            "category",
            "summary",
            "content",
            "usage_note",
            "source_name",
            "source_url",
            "source_type",
            "verification_status",
            "version",
            "is_featured",
            "sort_order",
        ):
            if field in payload:
                setattr(entry, field, payload[field])
        db.session.flush()
    db.session.commit()
    return {"created": created, "updated": updated, "total": KnowledgeEntry.query.count()}


def category_options() -> list[dict]:
    rows = (
        db.session.query(KnowledgeEntry.category, func.count(KnowledgeEntry.id))
        .filter(KnowledgeEntry.status == "published", KnowledgeEntry.verification_status == "verified")
        .group_by(KnowledgeEntry.category)
        .all()
    )
    counts = {row[0]: row[1] for row in rows}
    options = [{"value": key, "label": label, "count": counts.get(key, 0)} for key, label in CATEGORIES.items()]
    total = sum(counts.values())
    return [{"value": "all", "label": "全部", "count": total}] + options


def search(*, query: str = "", category: str = "all", page: int = 1, per_page: int = 12, featured_only: bool = False):
    query = clean_text(query, max_len=60, field="搜索关键词") or ""
    # C 端只允许展示“已发布且已核验”的内容，避免草稿/待核验数据成为幽灵条目
    stmt = KnowledgeEntry.query.filter(
        KnowledgeEntry.status == "published",
        KnowledgeEntry.verification_status == "verified",
    )
    if category and category != "all":
        stmt = stmt.filter(KnowledgeEntry.category == category)
    if featured_only:
        stmt = stmt.filter(KnowledgeEntry.is_featured.is_(True))
    if query:
        like = f"%{query}%"
        stmt = stmt.filter(
            or_(
                KnowledgeEntry.title.like(like),
                KnowledgeEntry.aliases.like(like),
                KnowledgeEntry.keywords.like(like),
                KnowledgeEntry.summary.like(like),
                KnowledgeEntry.content.like(like),
            )
        )
    stmt = stmt.order_by(KnowledgeEntry.sort_order.asc(), KnowledgeEntry.id.asc())
    pagination = stmt.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": [entry.to_public(brief=True) for entry in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "query": query,
        "category": category,
        "categories": category_options(),
    }


def get_by_id(entry_id: int) -> KnowledgeEntry | None:
    """公开详情只返回已发布条目；后台请直接查数据库。"""
    entry = db.session.get(KnowledgeEntry, entry_id)
    return (
        entry
        if entry is not None
        and entry.status == "published"
        and entry.verification_status == "verified"
        else None
    )


def get_by_slug(slug: str) -> KnowledgeEntry | None:
    return KnowledgeEntry.query.filter_by(slug=slug).first()


def match_names(names: list[str], *, limit: int = 2) -> dict[str, list[dict]]:
    """把配料名称匹配到知识库条目（精确 > 包含）。

    仅用于「解释参考」，匹配不到不代表该成分有问题。
    """
    entries = KnowledgeEntry.query.all()
    index: list[tuple[str, KnowledgeEntry]] = []
    for entry in entries:
        for alias in [entry.title, *[a for a in (entry.aliases or "").split(",") if a]]:
            idx = _norm(alias)
            if idx:
                index.append((idx, entry))

    result: dict[str, list[dict]] = {}
    for name in names:
        target = _norm(name)
        if not target:
            continue
        scored: dict[int, tuple[float, KnowledgeEntry]] = {}
        for alias_norm, entry in index:
            if target == alias_norm:
                score = 1.0
            elif len(alias_norm) >= 2 and alias_norm in target:
                score = 0.8
            elif len(target) >= 2 and target in alias_norm:
                score = 0.65
            else:
                continue
            current = scored.get(entry.id)
            if current is None or score > current[0]:
                scored[entry.id] = (score, entry)
        ranked = sorted(scored.values(), key=lambda item: -item[0])[:limit]
        result[name] = [
            {
                "id": entry.id,
                "slug": entry.slug,
                "title": entry.title,
                "category": entry.category,
                "category_label": CATEGORIES.get(entry.category, entry.category),
                "summary": entry.summary,
                "source_name": entry.source_name,
                "source_url": entry.source_url,
                "source_type": entry.source_type,
                "verification_status": entry.verification_status,
                "version": entry.version,
                "match_score": round(score, 2),
            }
            for score, entry in ranked
        ]
    return result


def knowledge_context(hits: list[dict], *, max_chars: int = 4000) -> str:
    """把命中的知识条目组织成给大模型的参考上下文。"""
    seen: set[int] = set()
    blocks: list[str] = []
    used = 0
    for hit in hits:
        if hit["id"] in seen:
            continue
        seen.add(hit["id"])
        entry = get_by_id(hit["id"])
        if not entry:
            continue
        block = (
            f"[K{entry.id}] {entry.title}\n"
            f"类别：{CATEGORIES.get(entry.category, entry.category)}\n"
            f"要点：{entry.summary}\n"
            f"说明：{entry.content}\n"
            f"来源：{entry.source_name}（版本 {entry.version}，核验状态：{entry.verification_status}）"
        )
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def stats() -> dict:
    total = KnowledgeEntry.query.count()
    verified = KnowledgeEntry.query.filter_by(verification_status="verified").count()
    pending = KnowledgeEntry.query.filter_by(verification_status="pending").count()
    return {"total": total, "verified": verified, "pending": pending, "categories": len(CATEGORIES)}


def find_local_entry(name: str) -> KnowledgeEntry | None:
    """按配料名精确优先查本地知识库（包含已核验与待核验缓存）。"""
    target = _norm(name)
    if not target:
        return None
    entries = KnowledgeEntry.query.all()
    fallback = None
    for entry in entries:
        aliases = [entry.title, *[a for a in (entry.aliases or "").split(",") if a]]
        for alias in aliases:
            value = _norm(alias)
            if not value:
                continue
            if value == target:
                return entry
            if len(value) >= 2 and (value in target or target in value):
                fallback = fallback or entry
    return fallback


def _insert_ai_entry(app, name: str, summary: str, content: str) -> None:
    """后台线程：把 AI 解释沉淀为待核验知识条目。"""
    try:
        with app.app_context():
            existing = KnowledgeEntry.query.filter(
                KnowledgeEntry.title == name,
                KnowledgeEntry.source_name.like("AI生成%"),
            ).first()
            if existing is not None:
                return
            slug = f"ai-{hashlib.md5(name.encode('utf-8')).hexdigest()[:14]}"
            if KnowledgeEntry.query.filter_by(slug=slug).first() is not None:
                return
            entry = KnowledgeEntry(
                slug=slug,
                title=name[:160],
                aliases=name[:300],
                keywords=name[:300],
                category="ingredient",
                summary=str(summary or "")[:500],
                content=str(content or summary or "")[:2000],
                usage_note="AI 自动沉淀，未经官方核实，请谨慎参考。",
                source_name="AI生成（待官方核实）",
                source_type="editorial",
                verification_status="pending",
                status="draft",
                scope="AI配料解释",
                created_by="AI",
                updated_by="AI",
            )
            db.session.add(entry)
            db.session.commit()
            logger.info("AI 配料解释已沉淀：%s", name)
    except Exception as exc:  # pragma: no cover - 后台失败不影响主流程
        logger.warning("AI 配料解释入库失败 %s：%s", name, exc.__class__.__name__)


def enqueue_ai_entry(name: str, summary: str, content: str) -> None:
    """异步写入，绝不阻塞分析结果返回。"""
    if not name or not summary:
        return
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_insert_ai_entry,
        args=(app, str(name)[:160], summary, content),
        daemon=True,
        name="knowledge-flywheel",
    )
    thread.start()
