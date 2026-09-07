"""Смоук-тест программы (запускается без дисплея).

Запуск:
    BOATAPP_DB=$PWD/tests/_run/smoke.db QT_QPA_PLATFORM=offscreen \
    LD_LIBRARY_PATH=$PWD/.qtlibs/usr/lib .venv/bin/python tests/smoke.py

Проверяет: создание схемы, статусы имущества, типовой перечень, акт осмотра,
удаление позиций/судов, построение главного окна, диалогов и сохранение PDF.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUN = HERE / "_run"
RUN.mkdir(exist_ok=True)

os.environ.setdefault("BOATAPP_DB", str(RUN / "smoke.db"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# подключаем src для импорта пакета boatapp
sys.path.insert(0, str(ROOT / "src"))

from boatapp import logic  # noqa: E402
from boatapp.db import SessionLocal, init_db  # noqa: E402
from boatapp.models import (  # noqa: E402
    EquipmentItem,
    Inspection,
    InspectionEntry,
    Ship,
)

# Приложение Qt нужно уже для печати/PDF (платформа offscreen задана выше)
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok  " if cond else "FAIL") + "  " + msg)
    if not cond:
        FAILURES.append(msg)


# ---------------------------------------------------------------------------
# БД для теста
# ---------------------------------------------------------------------------
db_file = RUN / "smoke.db"
for suffix in ("", "-journal", "-wal"):
    (RUN / f"smoke.db{suffix}").unlink(missing_ok=True)

init_db()
session = SessionLocal()

# ---------------------------------------------------------------------------
# 1. Демонстрационные данные
# ---------------------------------------------------------------------------
ship_id, inspection_id = logic.create_demo_data()
ship = session.get(Ship, ship_id)
check(ship is not None and ship.name == "Нептун", "демо-судно создано")

items = (
    session.query(EquipmentItem)
    .filter(EquipmentItem.ship_id == ship_id)
    .order_by(EquipmentItem.name)
    .all()
)
check(len(items) == len(logic.PRESET_ITEMS), f"добавлено позиций: {len(items)}")

by_name = {i.name: i for i in items}
checks = {
    "Спасательный жилет": logic.ST_SHORTAGE,
    "Аварийный радиобуй (АРБ/EPIRB 406 МГц)": logic.ST_TEST_OVERDUE,
    "Фальшфейер красный": logic.ST_EXPIRED,
    "Дымовая шашка плавучая (оранжевый дым)": logic.ST_EXPIRY_SOON,
}
for name, expected in checks.items():
    item = by_name.get(name)
    check(
        item is not None and item.status == expected,
        f"статус «{name}» = {expected} (факт: {item.status if item else 'нет'})",
    )

insp = session.get(Inspection, inspection_id)
check(insp is not None, "пример акта создан")
check(insp is not None and insp.number.startswith("АСИ-"), "номер акта заполнен")
check(insp is not None and insp.result == logic.RESULT_NOTES, "итог акта = «с замечаниями»")
if insp is not None:
    check(len(insp.entries) == len(items), "акт содержит все позиции")

# ---------------------------------------------------------------------------
# 2. Новый осмотр через perform_inspection
# ---------------------------------------------------------------------------
new_date = date.today() - timedelta(days=2)
# проверяем жилет (доукомплектовываем до 6) и ещё четыре позиции
targets = [
    "Спасательный жилет",
    "Спасательный круг",
    "Спасательный плот надувной",
    "Аптечка первой помощи",
    "Радиостанция УКВ носимая",
]
results = []
for name in targets:
    it = session.get(EquipmentItem, by_name[name].id)
    found = 6 if name == "Спасательный жилет" else (it.required_qty or 1)
    results.append(
        {
            "item_id": it.id,
            "found_qty": found,
            "state": logic.STATE_OK,
            "comment": "",
            "name": it.name,
            "location": it.location or "",
            "category": it.category or "",
        }
    )
insp2 = logic.perform_inspection(
    ship_id=ship_id,
    check_date=new_date,
    inspector="Тест-инспектор",
    results=results,
    summary="тестовый осмотр",
)
check(insp2.result == logic.RESULT_OK, "итог нового акта = без замечаний")
check(insp2.number != insp.number, "номера актов различны")
session.expire_all()
jilet = session.get(EquipmentItem, by_name["Спасательный жилет"].id)
check(jilet.actual_qty == 6, "фактическое количество обновлено по осмотру (6)")
check(jilet.last_test_date == new_date, "дата последней проверки обновлена")
check(jilet.status != logic.ST_SHORTAGE, "дефицит жилета устранён по статусу")

# ---------------------------------------------------------------------------
# 3. Удаление позиции не трогает историю актов
# ---------------------------------------------------------------------------
entry_count_before = (
    session.query(InspectionEntry)
    .filter(InspectionEntry.inspection_id == insp.id)
    .count()
)
target = by_name["Одеяло спасательное"]
target_id = target.id
session.delete(session.get(EquipmentItem, target_id))
session.commit()
entry_count_after = (
    session.query(InspectionEntry)
    .filter(InspectionEntry.inspection_id == insp.id)
    .count()
)
check(
    entry_count_after == entry_count_before,
    "строки актов сохранены после удаления позиции",
)
orphan = (
    session.query(InspectionEntry)
    .filter(
        InspectionEntry.inspection_id == insp.id,
        InspectionEntry.item_name == "Одеяло спасательное",
    )
    .first()
)
check(
    orphan is not None and orphan.item_id is None,
    "строка акта хранит «снимок» после удаления позиции (FK обнулён)",
)

# ---------------------------------------------------------------------------
# 4. HTML и PDF акта
# ---------------------------------------------------------------------------
from boatapp import reports  # noqa: E402

# акт грузим свежей сессией (как это делает предпросмотр в приложении)
insp2_fresh = reports.load_inspection(session, insp2.id)
html = reports.render_act_html(insp2_fresh)
check("АКТ ОСМОТРА" in html and "Тест-инспектор" in html, "HTML акта сформирован")

html_path = RUN / "act.html"
reports.save_act_html(html, html_path)
check(html_path.stat().st_size > 0, "HTML-копия акта сохранена")

pdf_path = RUN / "act.pdf"
ok_pdf = reports.save_act_pdf(html, pdf_path)
check(ok_pdf and pdf_path.stat().st_size > 0, "PDF акта сохранён (Qt)")

# ---------------------------------------------------------------------------
# 5. GUI: главное окно и диалоги
# ---------------------------------------------------------------------------
from boatapp.main_window import MainWindow  # noqa: E402
from boatapp.dialogs import ItemDialog  # noqa: E402
from boatapp.inspection_ui import ActPreviewDialog, InspectionDialog  # noqa: E402

win = MainWindow()
win._reload_ships(select_id=ship_id)
check(win.current_ship_id == ship_id, "главное окно выбрало демо-судно")
win._refresh_current_ship()
rows = win.table.rowCount()
check(rows == len(items) - 1, f"таблица заполнена: {rows} строк")

# статус-ячейки подсвечены
cell = win.table.item(0, 1)
check(cell is not None and cell.text(), "первая строка таблицы заполнена")

# поиск: скрываем строки, не содержащие «радиобуй»
win.ed_search.setText("радиобуй")
visible = sum(
    1 for r in range(win.table.rowCount()) if not win.table.isRowHidden(r)
)
check(visible == 1, f"поиск «радиобуй» оставил {visible} строку")
win.ed_search.setText("")

# диалог редактирования позиции строится с данными
item_for_dialog = session.get(EquipmentItem, items[0].id)
dlg_item = ItemDialog(None, item_for_dialog)
check(
    dlg_item.ed_name.text() == item_for_dialog.name,
    "ItemDialog заполнен данными позиции",
)
dlg_item.deleteLater()

# форма осмотра строится
dlg_check = InspectionDialog(None, ship.name, ship_id)
check(dlg_check.table.rowCount() == rows, "InspectionDialog показывает позиции")
dlg_check.deleteLater()

# предпросмотр акта строится и показывает HTML
dlg_prev = ActPreviewDialog(insp2.id)
check(
    "АКТ ОСМОТРА" in dlg_prev.browser.toPlainText(),
    "предпросмотр акта показывает документ",
)
dlg_prev.deleteLater()

# ---------------------------------------------------------------------------
# 5b. Регрессия: тёмная тема и PDF с родительским окном
# ---------------------------------------------------------------------------
from PySide6.QtGui import QColor, QPalette  # noqa: E402

# «включаем» тёмную тему через палитру Fusion
QApplication.setStyle("Fusion")
dark_palette = QPalette()
dark_palette.setColor(QPalette.ColorRole.Window, QColor(35, 36, 40))
dark_palette.setColor(QPalette.ColorRole.Base, QColor(28, 29, 33))
dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 36, 40))
dark_palette.setColor(QPalette.ColorRole.Text, QColor(235, 235, 235))
dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(235, 235, 235))
dark_palette.setColor(QPalette.ColorRole.Button, QColor(45, 46, 50))
dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(235, 235, 235))
dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(60, 100, 180))
dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
QApplication.instance().setPalette(dark_palette)

win._refresh_current_ship()
sample_ink = win.table.item(0, 2).foreground().color().lightness()
check(sample_ink > 128, f"текст ячеек светлый в тёмной теме (яркость {sample_ink})")
sample_status = win.table.item(0, 1).background().color()
check(
    sample_status.lightness() > 128,
    "фон колонки «Статус» остаётся светлым (читаем) в тёмной теме",
)

# сохранение PDF с окном-родителем — как в интерфейсе (регрессия setParent)
pdf_parent_path = RUN / "act_parent.pdf"
ok_parent = reports.save_act_pdf(html, pdf_parent_path, parent=win)
check(
    ok_parent and pdf_parent_path.stat().st_size > 0,
    "PDF сохранён с окном-родителем (нет ошибки setParent)",
)

# возвращаем светлую тему
QApplication.instance().setPalette(QApplication.style().standardPalette())
QApplication.setStyle("")

# ---------------------------------------------------------------------------
# 6. Удаление судна каскадом
# ---------------------------------------------------------------------------
session.delete(session.get(Ship, ship_id))
session.commit()
left = session.query(Ship).count()
check(left == 0, "судно удалено")
check(
    session.query(EquipmentItem).count() == 0
    and session.query(Inspection).count() == 0
    and session.query(InspectionEntry).count() == 0,
    "каскадное удаление данных судна",
)

session.close()
win.close()

print()
if FAILURES:
    print(f"Смоук-тест: ПРОВАЛЕНО проверок: {len(FAILURES)}")
    for f in FAILURES:
        print(" -", f)
    sys.exit(1)
print("Смоук-тест пройден успешно.")
