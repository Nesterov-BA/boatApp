"""Проверка выбора/настройки базы данных в изолированном процессе.

Использование (переменные окружения задаются ВНЕ скрипта, до импорта пакета):

    python tests/test_db_backends.py sqlite-default
    BOATAPP_DB=... python tests/test_db_backends.py sqlite-path
    BOATAPP_DB_URL=mysql+pymysql://u:p@h:3306/db python tests/test_db_backends.py url-mysql
    BOATAPP_DB_URL=postgresql+psycopg://u:p@h:1/db python tests/test_db_backends.py url-postgres-bad

Каждый запуск — отдельный процесс, чтобы настройки окружения применились
к модулю подключения при импорте. Сценарии url-* допускают два исхода:
драйвер СУБД не установлен (ожидаем понятную подсказку об установке) либо
установлен (проверяем диалект и маскирование пароля).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else ""


def main() -> None:
    try:
        from boatapp import db

        import_error = None
    except RuntimeError as exc:
        db = None
        import_error = exc

    if SCENARIO == "sqlite-default":
        assert import_error is None, import_error
        assert db.configured_url() is None, "URL сервера не должен быть задан"
        assert db.engine.dialect.name == "sqlite", "ожидался диалект sqlite"
        assert db.safe_database_url().startswith("sqlite:///"), "ожидался sqlite URL"
        assert db.DB_PATH.name == "boatapp.db", "файл по умолчанию boatapp.db"

    elif SCENARIO == "sqlite-path":
        assert import_error is None, import_error
        assert db.configured_url() is None, "BOATAPP_DB_URL не задан"
        assert db.engine.dialect.name == "sqlite"
        db.init_db()  # создаёт файл и таблицы
        from sqlalchemy import inspect

        tables = inspect(db.engine).get_table_names()
        assert {"ships", "equipment_items", "inspections",
                "inspection_entries"} <= set(tables), tables
        assert db.DB_PATH.exists(), f"файл БД не создан: {db.DB_PATH}"

    elif SCENARIO == "url-mysql":
        if import_error is not None:
            msg = str(import_error)
            assert "pymysql" in msg and "uv add pymysql" in msg, msg
            print("OK: url-mysql — понятная подсказка про драйвер pymysql")
            return
        assert db.engine.dialect.name == "mysql", "ожидался диалект mysql"
        safe = db.safe_database_url()
        assert "pw" not in safe and "mysql+pymysql://" in safe, safe

    elif SCENARIO == "url-postgres-bad":
        if import_error is not None:
            msg = str(import_error)
            assert "psycopg" in msg and "Не удалось подключиться" in msg, msg
            print("OK: url-postgres — понятная подсказка про драйвер psycopg")
            return
        assert db.engine.dialect.name == "postgresql", "ожидался диалект postgresql"
        try:
            db.check_connection()
        except RuntimeError as exc:
            assert "Не удалось подключиться" in str(exc), exc
            print("OK (ожидаемая ошибка подключения к недоступному серверу)")
            return
        except Exception as exc:
            raise AssertionError(f"неожиданная ошибка: {exc!r}") from exc
        raise AssertionError("ожидалась ошибка подключения, но её не было")

    else:
        raise SystemExit(f"неизвестный сценарий: {SCENARIO!r}")

    print(f"OK: {SCENARIO}")


if __name__ == "__main__":
    main()
