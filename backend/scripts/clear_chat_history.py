"""清空演示账号的 AI 食安智询官聊天测试历史。

只删除 ChatSession / ChatMessage，不影响知识库、收藏和分析记录。
运行：backend/.venv/Scripts/python.exe scripts/clear_chat_history.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import ChatSession, User  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username="demo").first()
        if user is None:
            print("demo 用户不存在")
            return
        sessions = ChatSession.query.filter_by(user_id=user.id).all()
        count = len(sessions)
        for session in sessions:
            db.session.delete(session)
        db.session.commit()
        print(f"cleared_sessions={count}")


if __name__ == "__main__":
    main()
