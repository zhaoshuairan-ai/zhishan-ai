"""Flask 扩展实例（单独文件避免循环导入）。"""
from __future__ import annotations

from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
cors = CORS()
