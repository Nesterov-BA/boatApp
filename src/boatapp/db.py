"""Подключение к базе данных SQLite и фабрики сессий."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def default_db_path() -> Path:
    """Путь к файлу БД: переменная BOATAPP_DB или файл рядом с проектом."""
    env = os.environ.get("BOATAPP_DB")
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_ROOT / "boatapp.db"


DB_PATH: Path = default_db_path()


def _url(path: Path) -> str:
    return f"sqlite:///{path}"


engine = create_engine(_url(DB_PATH), echo=False)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    """Включаем внешние ключи и WAL для надёжности и скорости."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Безопасно вызывать при каждом старте."""
    from . import models  # noqa: F401  (регистрирует модели в метаданных)

    Base.metadata.create_all(engine)
