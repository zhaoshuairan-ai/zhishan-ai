"""蓝图注册（全部挂在 /api 前缀下）。"""
from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .admin import bp as admin_bp
    from .analyze import bp as analyze_bp
    from .assistant import bp as assistant_bp
    from .auth import bp as auth_bp
    from .captcha import bp as captcha_bp
    from .dashboard import bp as dashboard_bp
    from .dishes import bp as dishes_bp
    from .favorites import bp as favorites_bp
    from .family import bp as family_bp
    from .health import bp as health_bp
    from .knowledge import bp as knowledge_bp
    from .ocr import bp as ocr_bp
    from .pantry import bp as pantry_bp
    from .records import bp as records_bp
    from .reports import bp as reports_bp
    from .settings_api import bp as settings_bp
    from .uploads import bp as uploads_bp

    for blueprint in (
        health_bp,
        auth_bp,
        captcha_bp,
        dashboard_bp,
        uploads_bp,
        ocr_bp,
        analyze_bp,
        records_bp,
        reports_bp,
        knowledge_bp,
        dishes_bp,
        assistant_bp,
        pantry_bp,
        favorites_bp,
        family_bp,
        admin_bp,
        settings_bp,
    ):
        app.register_blueprint(blueprint, url_prefix="/api")
