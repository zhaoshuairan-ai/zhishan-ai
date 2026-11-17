"""把商业条码库配置安全写入 .env（不把 Key 回显到终端）。

用法：
    python scripts/configure_barcode.py
    python scripts/configure_barcode.py --provider showapi

脚本会交互式询问 ShowAPI AppKey（输入时不显示），写入项目根目录 .env，
并提示你重启后端。不会把 Key 打到 stdout，也不会写入前端。
"""
from __future__ import annotations

import argparse
import getpass
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def update_env(path: Path, values: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    existing = {line.split("=", 1)[0].strip(): index for index, line in enumerate(lines) if "=" in line}
    for key, value in values.items():
        if key in existing:
            lines[existing[key]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="配置商业商品条码库")
    parser.add_argument("--provider", default="showapi", choices=["showapi", "generic", "auto", "none"])
    parser.add_argument("--app-key", default="", help="ShowAPI AppKey；不建议直接写在命令历史里")
    parser.add_argument("--url", default="", help="自定义条码库 URL（{barcode} 占位）")
    parser.add_argument("--api-key", default="", help="自定义条码库 Key")
    args = parser.parse_args()

    if not ENV_PATH.exists():
        print(f"未找到 {ENV_PATH}，请先按 README 创建 .env。")
        return 1

    app_key = args.app_key.strip()
    if args.provider == "showapi" and not app_key:
        print("请粘贴 ShowAPI AppKey（输入时不显示，直接回车取消）：")
        try:
            app_key = getpass.getpass("SHOWAPI_APP_KEY: ").strip()
        except (EOFError, KeyboardInterrupt):
            app_key = ""
    if args.provider == "showapi" and not app_key:
        print("未输入 AppKey，未做修改。")
        return 1
    if args.provider == "generic" and not args.url.strip():
        print("generic 模式需要 --url，例如 https://api.example.com/product/{barcode}")
        return 1

    backup = ENV_PATH.with_name(f".env.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(ENV_PATH, backup)
    values = {"BARCODE_PROVIDER": args.provider}
    if app_key:
        values["SHOWAPI_APP_KEY"] = app_key
    if args.provider == "generic":
        values["BARCODE_API_URL"] = args.url.strip()
        values["BARCODE_API_KEY"] = args.api_key.strip()
    update_env(ENV_PATH, values)
    print(f"已写入 {ENV_PATH}")
    print(f"原文件备份：{backup.name}")
    print("下一步：重启后端，然后运行：")
    print("  .\\backend\\.venv\\Scripts\\python.exe scripts\\check_barcode.py 6954767410388")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
