"""安全初始化管理员账号。

要求：
- 不在代码、README 或默认配置里写死任何管理员密码；
- 首次创建时由操作者输入密码（交互式），或使用 --random 生成一次性强密码；
- 密码使用 scrypt 哈希存储，脚本只输出一次明文（随机模式），不落盘；
- 支持把已有普通账号提升为管理员（--promote），不会静默覆盖。

用法：
    python scripts/create_admin.py --username admin
    python scripts/create_admin.py --username admin --display-name 管理员 --random
    python scripts/create_admin.py --username admin --promote      # 把已有账号提升为管理员并重设密码
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402
from app.seed.init_db import _ensure_columns  # noqa: E402
from app.services.admin_service import create_admin, validate_admin_password  # noqa: E402
from app.utils.errors import APIError  # noqa: E402


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in password) and any(c.isupper() for c in password) and any(
            c.isdigit() for c in password
        ):
            return password


def _ask_password() -> str:
    if not sys.stdin.isatty():
        print("[错误] 当前不是交互式终端：请使用 --random 生成随机密码，或通过标准输入管道提供密码。")
        raise SystemExit(2)
    while True:
        first = getpass.getpass("请输入管理员密码（至少 10 位，含字母和数字）：")
        try:
            validate_admin_password(first)
        except APIError as exc:
            print(f"[校验失败] {exc.message}")
            continue
        second = getpass.getpass("请再次输入以确认：")
        if first != second:
            print("[校验失败] 两次输入不一致，请重试。")
            continue
        return first


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化管理员账号（不写入任何默认密码）")
    parser.add_argument("--username", default="admin", help="管理员用户名（默认 admin）")
    parser.add_argument("--display-name", default="", help="显示名称")
    parser.add_argument("--email", default=None, help="邮箱（可选）")
    parser.add_argument("--random", action="store_true", help="生成一次性随机密码并打印")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="从标准输入读取密码（用于自动化/容器，不写入命令历史）",
    )
    parser.add_argument("--promote", action="store_true", help="把已存在的普通账号提升为管理员并重设密码")
    parser.add_argument(
        "--allow-weak",
        action="store_true",
        help="允许弱密码（仅本地演示；会打印明显警告，不要在生产使用）",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db.create_all()
        _ensure_columns()

        existing = User.query.filter_by(username=args.username).first()
        if existing and existing.role == "admin" and not args.promote:
            print(
                f"[提示] 管理员 {args.username} 已存在。"
                "如需重置密码，请加 --promote 重新设置；不要重复执行创建流程。"
            )
            return 1
        if existing and existing.role != "admin" and not args.promote:
            print(
                f"[提示] 用户名 {args.username} 已被普通用户占用。"
                "如确认要提升该账号，请加 --promote（会同时重设密码）。"
            )
            return 1

        if args.random:
            password = _random_password()
        elif args.password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
            if not password:
                print("[错误] 标准输入没有读到密码")
                return 2
        else:
            password = _ask_password()
        try:
            user, created = create_admin(
                args.username,
                password,
                display_name=args.display_name,
                email=args.email,
                promote=args.promote,
                allow_weak=args.allow_weak,
            )
        except APIError as exc:
            print(f"[失败] {exc.message}")
            return 2

        print("=" * 56)
        print(f"管理员账号已{'创建' if created else '更新'}：{user.username}（id={user.id}）")
        if args.allow_weak:
            print("⚠ 你使用了 --allow-weak：该密码不满足管理员密码强度策略，仅限本地演示，请勿用于生产。")
        if args.random:
            print(f"一次性密码：{password}")
            print("请立即登录并妥善保管；该密码只显示这一次，不会写入任何文件。")
        else:
            print("密码已按你输入的内容设置（不显示、不落盘）。")
        print("登录地址：/admin/login")
        print("=" * 56)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
