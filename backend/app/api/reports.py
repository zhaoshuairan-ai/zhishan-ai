"""报告接口：返回完整报告数据（前端负责打印 / 另存 PDF）。"""
from __future__ import annotations

from flask import Blueprint, current_app

from ..models import AnalysisRecord
from ..rules.label_rules import RULESET
from ..services import analysis_service, knowledge_service
from ..services.checker import OVERALL_LABELS
from ..utils.errors import ConflictError
from ..utils.response import ok
from ..utils.security import login_required, owned_or_404

bp = Blueprint("reports", __name__)


@bp.get("/reports/<int:record_id>")
@login_required
def get_report(record_id: int):
    record = owned_or_404(AnalysisRecord, record_id)
    if record.status != "analyzed" or record.ingredient is None:
        raise ConflictError("该记录尚未完成分析，无法生成报告", details={"status": record.status})

    report_meta = analysis_service.ensure_report(record)
    detail = analysis_service.build_detail(record)

    # 汇总知识来源（去重）
    sources: list[dict] = []
    seen: set[int] = set()

    def _add_source(entry_id: int | None, fallback: dict | None = None):
        if entry_id is not None and entry_id not in seen:
            entry = knowledge_service.get_by_id(entry_id)
            if entry:
                seen.add(entry_id)
                sources.append(
                    {
                        "id": entry.id,
                        "title": entry.title,
                        "source_name": entry.source_name,
                        "source_url": entry.source_url,
                        "source_type": entry.source_type,
                        "verification_status": entry.verification_status,
                        "version": entry.version,
                        "used_for": "配料解读",
                    }
                )
                return
        if fallback and fallback.get("title"):
            sources.append({**fallback, "used_for": fallback.get("used_for", "配料解读")})

    ingredient = record.ingredient
    for citation in ingredient.citations or []:
        _add_source(citation.get("knowledge_id"), citation)
    for explain in ingredient.ingredients or []:
        for ref in explain.get("knowledge_refs") or []:
            _add_source(ref.get("id"))

    # 核查规则依据（按来源名称去重）
    rule_sources: dict[str, dict] = {}
    for item in (record.check.items if record.check else []) or []:
        source = item.get("source") or {}
        name = source.get("name")
        if not name:
            continue
        rule_sources.setdefault(
            name,
            {
                "name": name,
                "type": source.get("type"),
                "note": source.get("note"),
                "rule_ids": [],
            },
        )
        rule_sources[name]["rule_ids"].append(item.get("rule_id"))

    return ok(
        {
            "report": report_meta.to_public(),
            "record": detail["record"],
            "ocr": detail["ocr"],
            "ingredient": detail["ingredient"],
            "nutrition": detail["nutrition"],
            "check": detail["check"],
            "health": detail.get("health"),
            "check_overall_label": OVERALL_LABELS.get(record.check.overall if record.check else "", ""),
            "sources": sources,
            "rule_sources": list(rule_sources.values()),
            "ruleset": {
                "version": RULESET["version"],
                "updated_at": RULESET["updated_at"],
                "disclaimer": RULESET["disclaimer"],
            },
            "meta": {
                **detail["meta"],
                "app_name": current_app.config["APP_NAME"],
                "app_subtitle": current_app.config["APP_SUBTITLE"],
                "app_version": current_app.config["APP_VERSION"],
                "public_site_url": current_app.config.get("PUBLIC_SITE_URL") or None,
            },
        }
    )
