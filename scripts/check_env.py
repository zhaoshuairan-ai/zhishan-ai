"""环境自检脚本：帮助初学者确认依赖是否装好。

用法（在项目根目录）：
    backend\\.venv\\Scripts\\python.exe scripts\\check_env.py
或使用系统 Python：
    python scripts/check_env.py
"""
from __future__ import annotations

import importlib
import os
import shutil
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"

results: list[tuple[str, str, str]] = []


def record(level: str, name: str, detail: str) -> None:
    results.append((level, name, detail))


def check_python() -> None:
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 11):
        record(OK, "Python 版本", version)
    else:
        record(FAIL, "Python 版本", f"{version}（需要 3.11 及以上）")


def check_modules() -> None:
    modules = [
        ("flask", "Flask"),
        ("flask_cors", "Flask-Cors"),
        ("flask_sqlalchemy", "Flask-SQLAlchemy"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pydantic", "Pydantic"),
        ("dotenv", "python-dotenv"),
        ("requests", "requests"),
        ("PIL", "Pillow"),
    ]
    for module, label in modules:
        try:
            importlib.import_module(module)
            record(OK, f"依赖 {label}", "已安装")
        except Exception:
            record(FAIL, f"依赖 {label}", "未安装（请执行 pip install -r backend/requirements.txt）")

    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401

        record(OK, "本地 OCR（rapidocr-onnxruntime）", "已安装，可离线识别中文标签")
    except Exception:
        record(WARN, "本地 OCR（rapidocr-onnxruntime）", "未安装 → 将回退到演示/视觉模型模式")

    try:
        import pytest  # noqa: F401

        record(OK, "测试框架 pytest", "已安装")
    except Exception:
        record(WARN, "测试框架 pytest", "未安装（可选，运行测试需要）")


def check_node() -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node:
        import subprocess

        try:
            version = subprocess.check_output([node, "--version"], text=True).strip()
            record(OK, "Node.js", version)
        except Exception:
            record(WARN, "Node.js", "已找到但无法执行")
    else:
        record(FAIL, "Node.js", "未安装或不在 PATH（前端需要 Node.js 18+）")
    record(OK if npm else WARN, "npm", "已安装" if npm else "未找到（若使用 pnpm 可忽略）")


def check_files() -> None:
    env_file = ROOT / ".env"
    record(OK if env_file.exists() else WARN, ".env 配置文件", "已存在" if env_file.exists() else "不存在（start.bat 会自动复制 .env.example）")
    db_file = ROOT / "data" / "food_safety.db"
    record(OK if db_file.exists() else WARN, "数据库文件", str(db_file) if db_file.exists() else "未初始化（运行 backend/init_db.py）")
    dist = ROOT / "frontend" / "dist" / "index.html"
    record(OK if dist.exists() else WARN, "前端构建产物", "已构建" if dist.exists() else "未构建（生产模式需要 npm run build）")


def check_ports() -> None:
    for port, label in ((5000, "后端"), (5173, "前端开发服务器")):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            in_use = sock.connect_ex(("127.0.0.1", port)) == 0
        record(OK if in_use else WARN, f"端口 {port}（{label}）", "正在监听" if in_use else "空闲")


def check_env_vars() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.config import Config

        record(OK if Config.AI_API_KEY else WARN, "AI_API_KEY", "已配置（大模型模式）" if Config.AI_API_KEY else "未配置（使用基础规则模式）")
        record(
            OK if Config.OCR_VISION_API_KEY else WARN,
            "OCR_VISION_API_KEY",
            "已配置（视觉模型 OCR）" if Config.OCR_VISION_API_KEY else "未配置（使用本地 OCR 或演示模式）",
        )
        record(OK, "OCR_PROVIDER", Config.OCR_PROVIDER)
        record(OK, "数据库地址", Config.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "sqlite: "))
        record(OK if "change-this" not in Config.SECRET_KEY else WARN, "SECRET_KEY", "使用默认值（生产环境必须修改）" if "change-this" in Config.SECRET_KEY else "已自定义")
    except Exception as exc:  # pragma: no cover
        record(WARN, "读取 .env 配置", f"失败：{exc.__class__.__name__}")


def main() -> int:
    print("=" * 62)
    print(" 智膳 AI · 环境自检")
    print(f" 项目目录：{ROOT}")
    print("=" * 62)
    check_python()
    check_modules()
    check_node()
    check_files()
    check_ports()
    check_env_vars()

    for level, name, detail in results:
        print(f"{level} {name:<32} {detail}")

    failures = [item for item in results if item[0] == FAIL]
    warnings = [item for item in results if item[0] == WARN]
    print("-" * 62)
    print(f"检查完成：{len(results)} 项，失败 {len(failures)} 项，提示 {len(warnings)} 项")
    if failures:
        print("\n需要先解决的问题：")
        for _, name, detail in failures:
            print(f"  - {name}：{detail}")
        print("\n参考 README.md 的「Windows 本地运行」章节。")
        return 1
    print("\n环境可用。运行 start.bat 即可启动网站。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
