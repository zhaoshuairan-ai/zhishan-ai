"""清理「AI 食安智询官」里的生硬测试会话，并补充两条真实科普提问。

运行：backend/.venv/Scripts/python.exe scripts/clean_assistant_history.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import ChatMessage, ChatSession, User  # noqa: E402
from app.services import assistant_service  # noqa: E402

TEST_WORDS = ("酒和头孢", "食物相克", "酒和海鲜")
REAL_QUESTIONS = (
    "阿斯巴甜真的致癌吗",
    "隔夜菜放冰箱怎么保存",
)


def main() -> None:
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username="demo").first()
        if user is None:
            print("demo 用户不存在")
            return
        removed = 0
        for session in ChatSession.query.filter_by(user_id=user.id).all():
            hits = [message for message in session.messages if any(word in (message.content or "") for word in TEST_WORDS)]
            if any(word in (session.title or "") for word in TEST_WORDS) or hits:
                db.session.delete(session)
                removed += 1
        db.session.commit()

        created = 0
        for question in REAL_QUESTIONS:
            exists = ChatSession.query.filter_by(user_id=user.id, title=question).first()
            if exists:
                continue
            try:
                assistant_service.ask(question, user.id)
                created += 1
            except Exception as exc:  # pragma: no cover
                print(f"补充问题失败：{question}：{exc.__class__.__name__}")
        print(f"removed={removed} created={created}")


if __name__ == "__main__":
    main()
