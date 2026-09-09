"""Программа учёта и проверки аварийно-спасательного имущества на судах."""

from __future__ import annotations

import os
import sys

APP_NAME = "АСИ · Учёт и проверка имущества на судах"
ORG_NAME = "BoatApp"

_HELP_TEXT = """\
АСИ — учёт и проверка аварийно-спасательного имущества на судах

Использование:
  python main.py [--db-url URL] [--check-db] [--help]

Параметры:
  --db-url URL   URL базы данных (переопределяет BOATAPP_DB_URL).
                 Примеры:
                   sqlite:///C:/data/boat.db
                   postgresql+psycopg://user:pass@host:5432/boatdb
                   mysql+pymysql://user:pass@host:3306/boatdb?charset=utf8mb4
  --check-db     Проверить подключение к базе и выйти (без запуска окна).
  --help         Эта справка.

База данных также задаётся переменными окружения BOATAPP_DB_URL,
BOATAPP_DB (путь к SQLite) или файлом boatapp.env рядом с приложением.
Подробности — в README.md, раздел «База данных на сервере».
"""


def _cli_check(argv: list[str]) -> int:
    try:
        from .db import check_connection

        message = check_connection()
    except Exception as exc:
        print(f"ОШИБКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ\n{exc}", file=sys.stderr)
        return 2
    print(f"Подключение к базе данных установлено: {message}.")
    print("Таблицы будут созданы автоматически при первом запуске программы.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа графического приложения (PySide6)."""
    args = list(sys.argv[1:] if argv is None else argv)

    if "--help" in args or "-h" in args:
        print(_HELP_TEXT)
        return 0

    # --db-url=URL или --db-url URL переопределяет настройку базы данных
    if "--db-url" in args:
        try:
            index = args.index("--db-url")
            url = args[index + 1]
        except IndexError:
            print("--db-url требует значение: --db-url sqlite:///путь/файл.db",
                  file=sys.stderr)
            return 2
        os.environ["BOATAPP_DB_URL"] = url

    if "--check-db" in args or "-c" in args:
        return _cli_check(args)

    from PySide6.QtWidgets import QApplication

    app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    try:
        from .db import has_explicit_config

        # Первый запуск без настроенной базы — диалог настройки в GUI,
        # консоль пользователю не нужна.
        if not has_explicit_config():
            from .db_setup import run_db_setup_dialog

            if not run_db_setup_dialog(first_run=True):
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    None,
                    "АСИ",
                    "Программа закрыта: база данных не настроена.\n"
                    "Запустите программу снова и выберите хранилище данных.",
                )
                return 0

        from .db import init_db

        init_db()
    except Exception as exc:
        # показываем понятное сообщение, если база недоступна
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(None, "База данных недоступна", str(exc))
        return 1

    from .main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()
