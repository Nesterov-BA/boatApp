"""Проверка GUI-диалога настройки базы данных (первый запуск).

Запуск (изолированный процесс, чтобы не задеть основную БД):

    BOATAPP_ENV_FILE=$PWD/tests/_run/setup_config.env \
    XDG_CONFIG_HOME=$PWD/tests/_run/xdg_config \
    QT_QPA_PLATFORM=offscreen \
    LD_LIBRARY_PATH=$PWD/.qtlibs/usr/lib \
    .venv/bin/python tests/test_db_setup_gui.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

for name in ("BOATAPP_DB_URL", "BOATAPP_DB"):
    os.environ.pop(name, None)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(ROOT / "src"))

RUN = HERE / "_run"
RUN.mkdir(exist_ok=True)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok  " if cond else "FAIL") + "  " + msg)
    if not cond:
        failures.append(msg)


def main() -> None:
    from boatapp import db
    from boatapp.db_setup import compose_server_url

    # чистый старт: настройка ещё не выполнялась
    target = Path(os.environ["BOATAPP_ENV_FILE"])
    target.unlink(missing_ok=True)
    check(not db.has_explicit_config(), "база ещё не настроена (первый запуск)")

    # --- составление URL (чистая функция) ----------------------------------
    url_mysql = compose_server_url(
        "mysql+pymysql", "db.example.com", 3306, "boat db", "пользователь",
        "пароль&слово",
    )
    check(
        url_mysql.startswith("mysql+pymysql://") and "?charset=utf8mb4" in url_mysql,
        f"URL MySQL собран корректно: {url_mysql[:60]}…",
    )
    check(
        "%D0%" in url_mysql and "пользователь" not in url_mysql
        and "пароль&слово" not in url_mysql,
        "кириллица/спецсимволы экранируются в URL",
    )
    url_pg = compose_server_url(
        "postgresql+psycopg", "10.0.0.5", 5432, "boatdb", "user", "secret"
    )
    check(
        url_pg == "postgresql+psycopg://user:secret@10.0.0.5:5432/boatdb",
        "URL PostgreSQL собран корректно",
    )

    # --- GUI-диалог: локальная база ----------------------------------------
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([])

    from boatapp.db_setup import DbSetupDialog

    dlg = DbSetupDialog(None, first_run=True)
    local_db = RUN / "gui_local.db"
    dlg.rb_local.setChecked(True)
    dlg.ed_path.setText(str(local_db))

    ok, desc = dlg.try_connect()
    check(ok, f"подключение локальной БД успешно: {desc}")
    check(
        db.engine.dialect.name == "sqlite" and "gui_local.db" in desc,
        "активная база переключена на выбранный SQLite-файл",
    )

    # сохранение настроек — как кнопка «Проверить и сохранить»
    dlg._on_save()
    check(dlg.result() == QDialog.DialogCode.Accepted, "диалог принял настройку")
    check(target.exists(), f"файл настроек создан: {target}")
    content = target.read_text(encoding="utf-8")
    check("BOATAPP_DB=" in content and "gui_local.db" in content,
          "в файл настроек записан путь к локальной БД")
    check(db.has_explicit_config(), "после сохранения база считается настроенной")

    # таблицы созданы автоматически
    from sqlalchemy import inspect

    tables = inspect(db.engine).get_table_names()
    check(
        {"ships", "equipment_items", "inspections", "inspection_entries"}
        <= set(tables),
        "схема создана автоматически",
    )

    # --- GUI-диалог: сервер недоступен/без драйвера --------------------------
    dlg2 = DbSetupDialog(None, first_run=False)
    dlg2.rb_server.setChecked(True)
    dlg2.cb_backend.setCurrentIndex(0)  # PostgreSQL
    dlg2.ed_host.setText("127.0.0.1")
    dlg2.sp_port.setValue(1)
    dlg2.ed_database.setText("nope")
    dlg2.ed_user.setText("user")
    dlg2.ed_password.setText("pw")
    ok2, err2 = dlg2.try_connect()
    check(
        not ok2 and ("Не удалось подключиться" in err2 or "psycopg" in err2),
        "недоступный сервер даёт понятную ошибку без падения",
    )
    check(
        db.engine.dialect.name == "sqlite" and "gui_local.db" in db.describe_backend(),
        "при неудаче активная база не меняется",
    )

    # проверка: dialog умеет валидировать пустые поля
    dlg3 = DbSetupDialog(None, first_run=False)
    dlg3.rb_server.setChecked(True)
    ok3, err3 = dlg3.try_connect()
    check(not ok3 and "host" in err3, "валидация пустых полей сервера")

    dlg.deleteLater()
    dlg2.deleteLater()
    dlg3.deleteLater()
    app.processEvents()

    # очистка артефактов теста
    target.unlink(missing_ok=True)
    for suffix in ("", "-journal", "-wal"):
        Path(str(local_db) + suffix).unlink(missing_ok=True)

    print()
    if failures:
        print(f"ПРОВАЛЕНО проверок: {len(failures)}")
        for msg in failures:
            print(" -", msg)
        sys.exit(1)
    print("Тест GUI-настройки базы данных пройден успешно.")


if __name__ == "__main__":
    main()
