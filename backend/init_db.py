"""数据库初始化脚本（Windows 下可直接运行）。

用法：
    .venv\\Scripts\\python.exe init_db.py
    .venv\\Scripts\\python.exe init_db.py --no-demo   # 不生成演示数据
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app  # noqa: E402
from app.seed.init_db import init_database  # noqa: E402


def main() -> int:
    with_demo = "--no-demo" not in sys.argv
    try:
        app = create_app()
    except Exception as exc:
        print("[错误] 应用初始化失败：", exc.__class__.__name__, exc)
        print("请检查 .env 配置（SECRET_KEY、DATABASE_URL、UPLOAD_DIR）是否正确。")
        return 1

    with app.app_context():
        try:
            result = init_database(verbose=True, with_demo_data=with_demo)
        except Exception as exc:  # pragma: no cover
            print("[错误] 数据库初始化失败：", exc.__class__.__name__, exc)
            print("若修改过模型字段，请删除 data/food_safety.db 后重新初始化（会丢失已有数据）。")
            return 1

    print("=" * 60)
    print(result["message"])
    print(f"数据库文件：{app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')}")
    print(f"图片目录：  {app.config['UPLOAD_DIR']}")
    if result["demo_user"].get("username"):
        print(f"演示账号：  {result['demo_user']['username']} / 密码见 .env 中 DEMO_PASSWORD")
    print("=" * 60)
    print("下一步：python wsgi.py 启动后端（默认 http://127.0.0.1:8000）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
