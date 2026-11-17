"""WSGI 入口：python wsgi.py 直接启动；生产环境可用 waitress-serve wsgi:app。"""
from __future__ import annotations

import os

from app import create_app
from app.config import Config

app = create_app()


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    if debug:
        app.logger.warning("调试模式已开启，请勿用于生产环境")
    print(f"\n{Config.APP_NAME} 后端已启动：http://127.0.0.1:{port}")
    print(f"局域网访问：http://<本机局域网IP>:{port}（手机与电脑需在同一 Wi-Fi）")
    print(f"健康检查：http://127.0.0.1:{port}/api/health\n")
    app.run(host=host, port=port, debug=debug, use_reloader=debug)
