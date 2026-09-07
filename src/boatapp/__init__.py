"""Программа учёта и проверки аварийно-спасательного имущества на судах."""

from __future__ import annotations

import sys

APP_NAME = "АСИ · Учёт и проверка имущества на судах"
ORG_NAME = "BoatApp"


def main(argv: list[str] | None = None) -> int:
    """Точка входа графического приложения (PySide6)."""
    from PySide6.QtWidgets import QApplication

    from .db import init_db

    init_db()

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    from .main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()
