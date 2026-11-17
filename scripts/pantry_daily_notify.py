"""每日 8:00 临期摘要通知（可接 Windows 任务计划 / cron）。

用法：
    python scripts/pantry_daily_notify.py --dry-run     # 只统计，不发
    python scripts/pantry_daily_notify.py               # 发送一次
    python scripts/pantry_daily_notify.py --loop        # 常驻，每天 08:00 发送

未配置 SMTP / 企业微信 / 钉钉时不会假装发送：摘要写入 data/notifications/*.log，
返回结果标记 simulated，便于本地演示与排查。
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.services.notify_service import send_daily_digests  # noqa: E402


def _next_run(at: str) -> datetime:
    hour, minute = [int(part) for part in at.split(":", 1)]
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def run_once(dry_run: bool) -> int:
    app = create_app()
    with app.app_context():
        result = send_daily_digests(dry_run=dry_run)
    print(
        f"用户 {result['users']} 个，生成摘要 {result['notified']} 条，模拟发送 {result['simulated']} 条"
        + ("（dry-run）" if dry_run else "")
    )
    for item in result["details"]:
        print(f"  - {item['username']}: {item['status']} / {item['subject']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="食安卫士每日临期摘要")
    parser.add_argument("--dry-run", action="store_true", help="只统计不发送")
    parser.add_argument("--loop", action="store_true", help="常驻，每天定时发送")
    parser.add_argument("--at", default="08:00", help="发送时间 HH:MM，默认 08:00")
    args = parser.parse_args()

    if not args.loop:
        return run_once(args.dry_run)

    print(f"已启动每日通知，发送时间 {args.at}；按 Ctrl+C 退出。")
    while True:
        target = _next_run(args.at)
        wait = max(1, int((target - datetime.now()).total_seconds()))
        print(f"下一次发送：{target.isoformat(timespec='minutes')}（等待 {wait // 3600} 小时 {wait % 3600 // 60} 分）")
        try:
            time.sleep(wait)
            run_once(args.dry_run)
        except KeyboardInterrupt:
            print("已停止。")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
