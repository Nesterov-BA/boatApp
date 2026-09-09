"""Главное окно программы: таблица имущества, фильтры, действия."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import logic
from .db import SessionLocal
from .dialogs import ItemDialog, ShipDialog, ShipManagerDialog
from .inspection_ui import ActPreviewDialog, InspectionDialog, InspectionPickerDialog
from .models import EquipmentItem, Ship
from .ui_common import (
    default_cell_colors,
    fmt_date,
    is_dark_theme,
    panel_style,
    status_colors,
    status_hint,
)

# Колонки таблицы имущества (без учёта скрытого id)
_COLUMNS = [
    "Статус",
    "Группа",
    "Наименование",
    "Место хранения",
    "Треб.",
    "Факт.",
    "Ед.",
    "Срок годности",
    "Посл. освид.",
    "След. освид.",
    "Примечания",
]

_ROLE_ID = Qt.ItemDataRole.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.current_ship_id: int | None = None
        self._rows: list[EquipmentItem] = []
        self.setMinimumSize(1080, 560)
        self.resize(1280, 720)

        self._build_ui()
        self._reload_ships()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(8, 8, 8, 8)

        # --- Ряд 1: судно ------------------------------------------------
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Судно:"))
        self.combo_ship = QComboBox()
        self.combo_ship.setMinimumWidth(320)
        self.combo_ship.currentIndexChanged.connect(self._on_ship_changed)
        row1.addWidget(self.combo_ship)

        self.btn_ships = QPushButton("Суда…")
        self.btn_ships.setToolTip(
            "Список судов: добавить, изменить или удалить"
        )
        self.btn_ships.clicked.connect(self._manage_ships)
        row1.addWidget(self.btn_ships)

        row1.addStretch(1)

        self.btn_check = QPushButton("Осмотр (акт)…")
        self.btn_check.setToolTip("Провести проверку имущества судна и составить акт")
        self.btn_check.clicked.connect(self._start_inspection)
        row1.addWidget(self.btn_check)

        self.btn_acts = QPushButton("Акты / Печать…")
        self.btn_acts.setToolTip(
            "Журнал актов осмотра судна: просмотр, печать, сохранение в PDF"
        )
        self.btn_acts.clicked.connect(self._open_acts)
        row1.addWidget(self.btn_acts)
        lay.addLayout(row1)

        # --- Ряд 2: действия и фильтры ------------------------------------
        row2 = QHBoxLayout()
        self.btn_add = QPushButton("+ Позиция")
        self.btn_add.setToolTip("Добавить позицию имущества на судно")
        self.btn_add.clicked.connect(self._add_item)
        row2.addWidget(self.btn_add)

        self.btn_edit = QPushButton("Изменить…")
        self.btn_edit.clicked.connect(self._edit_item)
        row2.addWidget(self.btn_edit)

        self.btn_del = QPushButton("Удалить")
        self.btn_del.clicked.connect(self._delete_item)
        row2.addWidget(self.btn_del)

        self.btn_preset = QPushButton("Типовой перечень АСИ")
        self.btn_preset.setToolTip(
            "Добавить на судно типовой перечень аварийно-спасательного "
            "имущества (можно править после добавления)"
        )
        self.btn_preset.clicked.connect(self._load_presets)
        row2.addWidget(self.btn_preset)

        row2.addStretch(1)
        row2.addWidget(QLabel("Поиск:"))
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("наименование, место, примечания…")
        self.ed_search.setFixedWidth(220)
        self.ed_search.textChanged.connect(self._apply_filter)
        row2.addWidget(self.ed_search)

        row2.addWidget(QLabel("Группа:"))
        self.combo_group = QComboBox()
        self.combo_group.currentIndexChanged.connect(self._apply_filter)
        row2.addWidget(self.combo_group)
        lay.addLayout(row2)

        # --- Содержимое -----------------------------------------------------
        self.stack = QStackedWidget()

        # Страница 1: нет судов
        page_empty = QWidget()
        lay_empty = QVBoxLayout(page_empty)
        lay_empty.addStretch(1)
        title = QLabel(
            "Программа учёта и проверки аварийно-спасательного имущества судов"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        sub = QLabel(
            "Для начала добавьте судно или загрузите демонстрационные данные."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_dark_theme():
            sub.setStyleSheet("color: #aab2bc;")
        else:
            sub.setStyleSheet("color: #555;")
        btn_create = QPushButton("Создать судно…")
        btn_create.setMinimumWidth(260)
        btn_create.clicked.connect(self._add_ship)
        btn_demo = QPushButton("Загрузить демонстрационные данные")
        btn_demo.setMinimumWidth(260)
        btn_demo.setToolTip(
            "Создаст судно «Нептун» с типовым имуществом, несколькими "
            "отклонениями и примером акта осмотра"
        )
        btn_demo.clicked.connect(self._load_demo)
        center = QHBoxLayout()
        center.addStretch(1)
        center.addWidget(btn_create)
        center.addWidget(btn_demo)
        center.addStretch(1)
        lay_empty.addWidget(title)
        lay_empty.addWidget(sub)
        lay_empty.addSpacing(24)
        lay_empty.addLayout(center)
        lay_empty.addStretch(2)

        # Страница 2: таблица имущества
        page_table = QWidget()
        lay_table = QVBoxLayout(page_table)
        lay_table.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, len(_COLUMNS) + 1)
        headers = [""] + _COLUMNS  # скрытая колонка id
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(lambda *_: self._edit_item())
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)

        self.lbl_empty_items = QLabel(
            "На судне ещё нет позиций имущества.\n"
            "Нажмите «+ Позиция» или «Типовой перечень АСИ»."
        )
        self.lbl_empty_items.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ink = "#f2f4f7" if is_dark_theme() else "#666"
        self.lbl_empty_items.setStyleSheet(f"color: {ink}; padding: 24px;")

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(panel_style())

        lay_table.addWidget(self.lbl_empty_items)
        lay_table.addWidget(self.table)
        lay_table.addWidget(self.lbl_summary)

        self.stack.addWidget(page_empty)
        self.stack.addWidget(page_table)

        self.lbl_empty_items.setVisible(False)
        self.table.setVisible(True)

        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Статус-бар
        self.statusBar().showMessage("Готово.")

        # Меню настройки базы данных (без консоли)
        settings_menu = self.menuBar().addMenu("Настройки")
        act_db = settings_menu.addAction("База данных…")
        act_db.setToolTip(
            "Сменить хранилище данных: локальный SQLite или серверная СУБД"
        )
        act_db.triggered.connect(self._change_database)

    # ------------------------------------------------------------------
    # Данные: суда
    # ------------------------------------------------------------------

    def _reload_ships(self, select_id: int | None = None) -> None:
        keep = select_id
        session = SessionLocal()
        try:
            ships = session.query(Ship).order_by(Ship.name).all()
            current_text = self.combo_ship.currentText()
        finally:
            session.close()

        self.combo_ship.blockSignals(True)
        self.combo_ship.clear()
        for ship in ships:
            self.combo_ship.addItem(ship.name, ship.id)

        # выбор судна: переданный id → прежний → первый
        if keep is None and ships:
            idx = self.combo_ship.findText(current_text)
            if idx >= 0:
                keep = self.combo_ship.itemData(idx)
        if keep is None and ships:
            keep = self.combo_ship.itemData(0)

        if keep is not None:
            idx = self.combo_ship.findData(keep)
            if idx >= 0:
                self.combo_ship.setCurrentIndex(idx)

        self.combo_ship.blockSignals(False)

        if not ships:
            self.current_ship_id = None
            self.stack.setCurrentIndex(0)
            self._set_ship_actions_enabled(False)
        else:
            self.stack.setCurrentIndex(1)
            self._set_ship_actions_enabled(True)
            if self.combo_ship.currentIndex() >= 0:
                self.current_ship_id = self.combo_ship.itemData(
                    self.combo_ship.currentIndex()
                )
        self._refresh_current_ship()

    def _set_ship_actions_enabled(self, enabled: bool) -> None:
        for btn in (self.btn_add, self.btn_edit, self.btn_del,
                    self.btn_preset, self.btn_check, self.btn_acts):
            btn.setEnabled(enabled)

    def _current_ship(self) -> Ship | None:
        if self.current_ship_id is None:
            return None
        session = SessionLocal()
        try:
            return session.get(Ship, self.current_ship_id)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Данные: таблица имущества
    # ------------------------------------------------------------------

    def _on_ship_changed(self, index: int) -> None:
        if index < 0:
            return
        self.current_ship_id = self.combo_ship.itemData(index)
        self._refresh_current_ship()

    def _refresh_current_ship(self) -> None:
        """Пересчитывает статусы и наполняет таблицу текущего судна."""
        ship_id = self.current_ship_id
        self.table.setSortingEnabled(False)
        try:
            if ship_id is None:
                self._rows = []
            else:
                # актуализируем сохранённые статусы
                logic.refresh_ship_statuses(ship_id)
                session = SessionLocal()
                try:
                    ship = session.get(Ship, ship_id)
                    items = (
                        session.query(EquipmentItem)
                        .filter(EquipmentItem.ship_id == ship_id)
                        .order_by(EquipmentItem.category, EquipmentItem.name)
                        .all()
                    )
                    self._rows = list(items)
                    ship_name = ship.name if ship is not None else "—"
                finally:
                    session.close()

            self._fill_table()
            self._fill_group_filter()
            self._apply_filter()
            self._update_summary()

            ship_name = self._current_ship_name()
            if ship_id is None:
                self.setWindowTitle("АСИ · Учёт и проверка имущества на судах")
            else:
                self.setWindowTitle(
                    f"АСИ · {ship_name} — имущество и проверки"
                )
        finally:
            self.table.setSortingEnabled(True)

    def _current_ship_name(self) -> str:
        session = SessionLocal()
        try:
            if self.current_ship_id is None:
                return ""
            ship = session.get(Ship, self.current_ship_id)
            return ship.name if ship else ""
        finally:
            session.close()

    def _fill_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._rows))
        today = date.today()
        # читаемый цвет текста обычных ячеек — по текущей теме (тёмная/светлая)
        _, cell_ink = default_cell_colors()

        for row, item in enumerate(self._rows):
            code = logic.compute_status(item, today)
            bg, fg = status_colors(code)
            texts = [
                logic.STATUS_RU[code],
                item.category or "",
                item.name,
                item.location or "",
                str(item.required_qty if item.required_qty is not None else 0),
                str(item.actual_qty if item.actual_qty is not None else 0),
                item.unit or "",
                fmt_date(item.expiry_date),
                fmt_date(item.last_test_date),
                fmt_date(logic.next_test_date(item)),
                item.notes or "",
            ]
            id_cell = QTableWidgetItem()
            id_cell.setData(_ROLE_ID, item.id)
            self.table.setItem(row, 0, id_cell)

            for col, text in enumerate(texts, start=1):
                cell = QTableWidgetItem(text)
                cell.setData(_ROLE_ID, item.id)
                if col == 1:  # колонка «Статус» — пастельная плашка
                    cell.setBackground(QColor(bg))
                    cell.setForeground(QColor(fg))
                    cell.setToolTip(status_hint(item))
                else:
                    # явный читаемый цвет текста под текущую тему (фон — свой)
                    cell.setForeground(QColor(cell_ink))
                self.table.setItem(row, col, cell)

        self._resize_columns()

        has_items = len(self._rows) > 0
        self.lbl_empty_items.setVisible(not has_items)
        self.table.setVisible(has_items)
        self.btn_check.setEnabled(has_items and self.current_ship_id is not None)

    def _resize_columns(self) -> None:
        self.table.resizeColumnsToContents()
        # колонка «Наименование» — пошире
        name_col = 3
        if self.table.columnWidth(name_col) < 220:
            self.table.setColumnWidth(name_col, 260)
        for col in (1, 2, 6):
            if self.table.columnWidth(col) > 220:
                self.table.setColumnWidth(col, 220)

    def _fill_group_filter(self) -> None:
        current = self.combo_group.currentText()
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        self.combo_group.addItem("Все группы", "")
        groups = sorted({item.category for item in self._rows if item.category})
        for g in groups:
            self.combo_group.addItem(g, g)
        idx = self.combo_group.findText(current)
        if idx >= 0:
            self.combo_group.setCurrentIndex(idx)
        self.combo_group.blockSignals(False)

    def _apply_filter(self, *_args) -> None:
        text = self.ed_search.text().strip().lower()
        group = self.combo_group.currentData() or ""
        for row in range(self.table.rowCount()):
            item_id = self.table.item(row, 0).data(_ROLE_ID)
            item = next((i for i in self._rows if i.id == item_id), None)
            if item is None:
                self.table.setRowHidden(row, True)
                continue
            match_group = (not group) or (item.category == group)
            haystack = " ".join(
                [
                    item.name or "",
                    item.category or "",
                    item.location or "",
                    item.notes or "",
                ]
            ).lower()
            self.table.setRowHidden(row, not (match_group and text in haystack))

    def _update_summary(self) -> None:
        today = date.today()
        n = len(self._rows)
        shortage = expired = test_overdue = soon = 0
        for item in self._rows:
            flags = logic.item_flags(item, today)
            if logic.ST_EXPIRED in flags:
                expired += 1
            if logic.ST_TEST_OVERDUE in flags:
                test_overdue += 1
            if logic.ST_SHORTAGE in flags:
                shortage += 1
            if (
                logic.ST_EXPIRY_SOON in flags
                or logic.ST_TEST_SOON in flags
            ):
                soon += 1
        parts = [
            f"Позиций: {n}",
            f"дефицит: {shortage}",
            f"истёк срок годности: {expired}",
            f"просрочено освидетельствование: {test_overdue}",
            f"скоро (30 дней): {soon}",
        ]
        self.lbl_summary.setText("   ".join(parts))

    # ------------------------------------------------------------------
    # Действия: суда
    # ------------------------------------------------------------------

    def _add_ship(self) -> None:
        dlg = ShipDialog(self)
        if dlg.exec() != ShipDialog.DialogCode.Accepted:
            return
        session = SessionLocal()
        try:
            ship = Ship(**dlg.values())
            session.add(ship)
            session.commit()
            new_id = ship.id
        finally:
            session.close()
        self._reload_ships(new_id)

    def _manage_ships(self) -> None:
        dlg = ShipManagerDialog(self)
        dlg.changed.connect(self._on_ships_changed)
        dlg.exec()

    def _on_ships_changed(self) -> None:
        current = self.current_ship_id
        # если текущее судно удалили — выберем первое оставшееся
        session = SessionLocal()
        try:
            exists = (
                current is not None
                and session.get(Ship, current) is not None
            )
        finally:
            session.close()
        self._reload_ships(current if exists else None)

    def _change_database(self) -> None:
        """Смена хранилища через диалог «База данных…» (без консоли)."""
        from . import db
        from .db_setup import run_db_setup_dialog

        if not run_db_setup_dialog(self, first_run=False):
            return
        QMessageBox.information(
            self,
            "База данных",
            "Подключение к базе данных переключено.\n\n"
            f"Текущее подключение: {db.describe_backend()}",
        )
        # перезагружаем интерфейс из новой базы
        self.current_ship_id = None
        self._reload_ships()

    def _load_demo(self) -> None:
        ret = QMessageBox.question(
            self,
            "Демонстрационные данные",
            "Создать судно «Нептун» с типовым перечнем имущества, "
            "несколькими отклонениями и примером акта осмотра?\n\n"
            "Данные можно свободно удалить или изменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            ship_id, inspection_id = logic.create_demo_data()
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self, "Демо-данные", f"Ошибка при создании данных:\n{exc}"
            )
            return
        self._reload_ships(ship_id)
        dlg = ActPreviewDialog(inspection_id, parent=self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Действия: имущество
    # ------------------------------------------------------------------

    def _selected_item_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        cell = self.table.item(row, 0)
        if cell is None:
            return None
        return cell.data(_ROLE_ID)

    def _add_item(self) -> None:
        if self.current_ship_id is None:
            return
        dlg = ItemDialog(self)
        if dlg.exec() != ItemDialog.DialogCode.Accepted:
            return
        session = SessionLocal()
        try:
            item = EquipmentItem(
                ship_id=self.current_ship_id, **dlg.values()
            )
            logic.refresh_item_status(item)
            session.add(item)
            session.commit()
        finally:
            session.close()
        self._refresh_current_ship()
        self.statusBar().showMessage("Позиция добавлена.", 3000)

    def _edit_item(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            QMessageBox.information(
                self, "Имущество", "Выберите позицию в таблице."
            )
            return
        session = SessionLocal()
        try:
            item = session.get(EquipmentItem, item_id)
            if item is None:
                return
            dlg = ItemDialog(self, item)
            if dlg.exec() == ItemDialog.DialogCode.Accepted:
                for key, value in dlg.values().items():
                    setattr(item, key, value)
                logic.refresh_item_status(item)
                session.commit()
                edited = True
            else:
                edited = False
        finally:
            session.close()
        if edited:
            self._refresh_current_ship()
            self.statusBar().showMessage("Позиция обновлена.", 3000)

    def _delete_item(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            QMessageBox.information(
                self, "Имущество", "Выберите позицию в таблице."
            )
            return
        session = SessionLocal()
        try:
            item = session.get(EquipmentItem, item_id)
            if item is None:
                return
            ret = QMessageBox.question(
                self,
                "Удаление позиции",
                f"Удалить «{item.name}» с судна?\n\n"
                "Записи в ранее оформленных актах осмотра будут сохранены.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret == QMessageBox.StandardButton.Yes:
                session.delete(item)
                session.commit()
                deleted = True
            else:
                deleted = False
        finally:
            session.close()
        if deleted:
            self._refresh_current_ship()
            self.statusBar().showMessage("Позиция удалена.", 3000)

    def _load_presets(self) -> None:
        if self.current_ship_id is None:
            return
        ship = self._current_ship()
        name = ship.name if ship else "судно"
        ret = QMessageBox.question(
            self,
            "Типовой перечень АСИ",
            f"Добавить на судно «{name}» типовой перечень "
            "аварийно-спасательного имущества?\n\n"
            f"Будет добавлено позиций: {len(logic.PRESET_ITEMS)}.\n"
            "Дубликаты не исключаются — проверьте список после добавления.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        session = SessionLocal()
        try:
            added = logic.add_preset_items(session, self.current_ship_id)
            session.commit()
        finally:
            session.close()
        self._refresh_current_ship()
        self.statusBar().showMessage(
            f"Добавлено позиций: {added}.", 4000
        )

    # ------------------------------------------------------------------
    # Действия: осмотры и акты
    # ------------------------------------------------------------------

    def _start_inspection(self) -> None:
        if self.current_ship_id is None:
            return
        ship = self._current_ship()
        if ship is None:
            return
        if not self._rows:
            QMessageBox.information(
                self,
                "Осмотр",
                "На судне нет позиций имущества.\n"
                "Сначала добавьте имущество.",
            )
            return
        dlg = InspectionDialog(self, ship.name, ship.id)
        dlg.exec()
        self._refresh_current_ship()

    def _open_acts(self) -> None:
        if self.current_ship_id is None:
            return
        ship = self._current_ship()
        if ship is None:
            return
        dlg = InspectionPickerDialog(self, ship.name, ship.id)
        dlg.exec()
        self._refresh_current_ship()
