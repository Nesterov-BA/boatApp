"""Диалоги: карточка судна, список судов, карточка позиции имущества."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import logic
from .db import SessionLocal
from .models import EquipmentItem, Ship
from .ui_common import py_to_qdate, qdate_to_py

_DATE_FORMAT = "dd.MM.yyyy"


# --------------------------------------------------------------------------
# Карточка судна
# --------------------------------------------------------------------------


class ShipDialog(QDialog):
    """Создание или редактирование судна."""

    def __init__(self, parent: QWidget | None = None, ship: Ship | None = None):
        super().__init__(parent)
        self._ship = ship
        self.setWindowTitle("Судно" if ship is None else f"Судно: {ship.name}")
        self.resize(460, 0)

        form = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Например: «Нептун»")
        self.ed_type = QLineEdit()
        self.ed_type.setPlaceholderText("Маломерное судно, катер, яхта…")
        self.ed_call = QLineEdit()
        self.ed_call.setPlaceholderText("Позывной / регистрационный №")
        self.ed_port = QLineEdit()
        self.ed_port.setPlaceholderText("Порт (место) приписки")
        self.ed_notes = QPlainTextEdit()
        self.ed_notes.setFixedHeight(70)

        form.addRow("Название *:", self.ed_name)
        form.addRow("Тип судна:", self.ed_type)
        form.addRow("Позывной / №:", self.ed_call)
        form.addRow("Порт приписки:", self.ed_port)
        form.addRow("Примечания:", self.ed_notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

        if ship is not None:
            self.ed_name.setText(ship.name)
            self.ed_type.setText(ship.ship_type or "")
            self.ed_call.setText(ship.call_sign or "")
            self.ed_port.setText(ship.home_port or "")
            self.ed_notes.setPlainText(ship.notes or "")

    def _on_save(self) -> None:
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Судно", "Укажите название судна.")
            self.ed_name.setFocus()
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name": self.ed_name.text().strip(),
            "ship_type": self.ed_type.text().strip(),
            "call_sign": self.ed_call.text().strip(),
            "home_port": self.ed_port.text().strip(),
            "notes": self.ed_notes.toPlainText().strip(),
        }


# --------------------------------------------------------------------------
# Список судов (управление)
# --------------------------------------------------------------------------


class ShipManagerDialog(QDialog):
    """Список судов с добавлением, изменением и удалением."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Суда")
        self.resize(640, 380)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Название", "Тип", "Позывной / №", "Порт", "Позиций имущества"]
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda *_: self._edit())

        btn_add = QPushButton("Добавить…")
        btn_edit = QPushButton("Изменить…")
        btn_del = QPushButton("Удалить")
        btn_close = QPushButton("Закрыть")
        btn_add.clicked.connect(self._add)
        btn_edit.clicked.connect(self._edit)
        btn_del.clicked.connect(self._delete)
        btn_close.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addWidget(btn_add)
        btns.addWidget(btn_edit)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        btns.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addLayout(btns)

        self._reload()

    # -- вспомогательное ---------------------------------------------------

    def _current_ship_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _ship_names(self) -> list[str]:
        names: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                names.append(item.text())
        return names

    def _reload(self) -> None:
        self.table.setRowCount(0)
        session = SessionLocal()
        try:
            ships = session.query(Ship).order_by(Ship.name).all()
            for ship in ships:
                row = self.table.rowCount()
                self.table.insertRow(row)
                for col, text in enumerate(
                    [
                        ship.name,
                        ship.ship_type or "",
                        ship.call_sign or "",
                        ship.home_port or "",
                        str(len(ship.items)),
                    ]
                ):
                    cell = QTableWidgetItem(text)
                    if col == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, ship.id)
                    self.table.setItem(row, col, cell)
        finally:
            session.close()
        self.table.resizeColumnsToContents()

    # -- действия ----------------------------------------------------------

    def _add(self) -> None:
        dlg = ShipDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = SessionLocal()
            try:
                vals = dlg.values()
                ship = Ship(**vals)
                session.add(ship)
                session.commit()
            finally:
                session.close()
            self._reload()
            self.changed.emit()

    def _edit(self) -> None:
        ship_id = self._current_ship_id()
        if ship_id is None:
            QMessageBox.information(self, "Суда", "Выберите судно из списка.")
            return
        session = SessionLocal()
        try:
            ship = session.get(Ship, ship_id)
            if ship is None:
                return
            dlg = ShipDialog(self, ship)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                for key, value in dlg.values().items():
                    setattr(ship, key, value)
                session.commit()
        finally:
            session.close()
        self._reload()
        self.changed.emit()

    def _delete(self) -> None:
        ship_id = self._current_ship_id()
        if ship_id is None:
            QMessageBox.information(self, "Суда", "Выберите судно из списка.")
            return
        session = SessionLocal()
        try:
            ship = session.get(Ship, ship_id)
            if ship is None:
                return
            n_items = len(ship.items)
            n_acts = len(ship.inspections)
            ret = QMessageBox.question(
                self,
                "Удаление судна",
                f"Удалить судно «{ship.name}»?\n\n"
                f"Будут удалены позиции имущества: {n_items} шт.\n"
                f"И акты осмотра: {n_acts} шт.\n\nДействие необратимо.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret == QMessageBox.StandardButton.Yes:
                session.delete(ship)
                session.commit()
        finally:
            session.close()
        self._reload()
        self.changed.emit()


# --------------------------------------------------------------------------
# Карточка позиции имущества
# --------------------------------------------------------------------------


class ItemDialog(QDialog):
    """Создание или редактирование позиции аварийно-спасательного имущества."""

    def __init__(
        self,
        parent: QWidget | None = None,
        item: EquipmentItem | None = None,
    ):
        super().__init__(parent)
        self._item = item
        title = "Позиция имущества"
        if item is not None:
            title = f"Имущество: {item.name}"
        self.setWindowTitle(title)
        self.resize(560, 0)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.cb_category = QComboBox()
        self.cb_category.setEditable(True)
        self.cb_category.addItems(logic.CATEGORIES)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Наименование имущества")
        self.ed_location = QLineEdit()
        self.ed_location.setPlaceholderText("Место хранения / установки на судне")
        self.ed_unit = QLineEdit()
        self.ed_unit.setPlaceholderText("шт.")
        self.sp_required = QSpinBox()
        self.sp_required.setRange(0, 9999)
        self.sp_actual = QSpinBox()
        self.sp_actual.setRange(0, 9999)

        # Срок годности
        self.chk_expiry = QCheckBox("Указан срок годности")
        self.de_expiry = QDateEdit()
        self.de_expiry.setCalendarPopup(True)
        self.de_expiry.setDisplayFormat(_DATE_FORMAT)
        self.de_expiry.setDate(py_to_qdate(date.today()))
        self.de_expiry.setEnabled(False)
        self.chk_expiry.toggled.connect(self.de_expiry.setEnabled)
        expiry_row = QHBoxLayout()
        expiry_row.addWidget(self.chk_expiry)
        expiry_row.addWidget(self.de_expiry)
        expiry_row.addStretch(1)

        # Освидетельствование
        self.chk_test = QCheckBox("Есть освидетельствование (последняя дата)")
        self.de_test = QDateEdit()
        self.de_test.setCalendarPopup(True)
        self.de_test.setDisplayFormat(_DATE_FORMAT)
        self.de_test.setEnabled(False)
        self.chk_test.toggled.connect(self.de_test.setEnabled)
        test_row = QHBoxLayout()
        test_row.addWidget(self.chk_test)
        test_row.addWidget(self.de_test)
        test_row.addStretch(1)

        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(0, 1200)
        self.sp_interval.setSuffix(" мес.")
        self.sp_interval.setSpecialValueText("не требуется")
        self.sp_interval.setValue(12)

        self.ed_notes = QPlainTextEdit()
        self.ed_notes.setFixedHeight(60)

        self.lbl_status = QLabel(" ")
        self.lbl_status.setWordWrap(True)

        form.addRow("Группа:", self.cb_category)
        form.addRow("Наименование *:", self.ed_name)
        form.addRow("Место хранения:", self.ed_location)
        form.addRow("Требуется:", self.sp_required)
        form.addRow("Фактически:", self.sp_actual)
        form.addRow("Ед. изм.:", self.ed_unit)
        form.addRow("", expiry_row)
        form.addRow("", test_row)
        form.addRow("Периодичность проверки:", self.sp_interval)
        form.addRow("Примечания:", self.ed_notes)
        form.addRow("Текущий статус:", self.lbl_status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

        self._prefill()
        self._on_change()

        # обновляем предпросмотр статуса при любом изменении
        for widget in (self.sp_required, self.sp_actual, self.sp_interval):
            widget.valueChanged.connect(self._on_change)
        for widget in (self.de_expiry, self.de_test):
            widget.dateChanged.connect(self._on_change)
        self.chk_expiry.toggled.connect(self._on_change)
        self.chk_test.toggled.connect(self._on_change)

    # -- заполнение --------------------------------------------------------

    def _prefill(self) -> None:
        item = self._item
        if item is None:
            return
        idx = self.cb_category.findText(item.category)
        if idx >= 0:
            self.cb_category.setCurrentIndex(idx)
        else:
            self.cb_category.setEditText(item.category)
        self.ed_name.setText(item.name)
        self.ed_location.setText(item.location or "")
        self.sp_required.setValue(item.required_qty or 0)
        self.sp_actual.setValue(item.actual_qty or 0)
        self.ed_unit.setText(item.unit or "шт.")
        if item.expiry_date is not None:
            self.chk_expiry.setChecked(True)
            self.de_expiry.setDate(py_to_qdate(item.expiry_date))
        if item.last_test_date is not None:
            self.chk_test.setChecked(True)
            self.de_test.setDate(py_to_qdate(item.last_test_date))
        self.sp_interval.setValue(item.test_interval_months or 0)
        self.ed_notes.setPlainText(item.notes or "")

    # -- предпросмотр статуса ---------------------------------------------

    def _make_probe(self) -> EquipmentItem:
        # Не мутируем редактируемый объект — собираем «пробу» для расчёта статуса.
        probe = EquipmentItem(ship_id=0)
        probe.required_qty = self.sp_required.value()
        probe.actual_qty = self.sp_actual.value()
        probe.expiry_date = (
            qdate_to_py(self.de_expiry.date()) if self.chk_expiry.isChecked() else None
        )
        probe.last_test_date = (
            qdate_to_py(self.de_test.date()) if self.chk_test.isChecked() else None
        )
        probe.test_interval_months = (
            self.sp_interval.value() if self.sp_interval.value() else None
        )
        return probe

    def _on_change(self) -> None:
        probe = self._make_probe()
        code = logic.compute_status(probe)
        text = logic.STATUS_RU.get(code, code)
        self.lbl_status.setText(f"Статус: {text}")

    def _on_save(self) -> None:
        if not self.ed_name.text().strip():
            QMessageBox.warning(
                self, "Имущество", "Укажите наименование имущества."
            )
            self.ed_name.setFocus()
            return
        if not self.cb_category.currentText().strip():
            QMessageBox.warning(self, "Имущество", "Укажите группу имущества.")
            self.cb_category.setFocus()
            return
        self.accept()

    def values(self) -> dict:
        return {
            "category": self.cb_category.currentText().strip(),
            "name": self.ed_name.text().strip(),
            "location": self.ed_location.text().strip(),
            "required_qty": self.sp_required.value(),
            "actual_qty": self.sp_actual.value(),
            "unit": self.ed_unit.text().strip() or "шт.",
            "expiry_date": (
                qdate_to_py(self.de_expiry.date())
                if self.chk_expiry.isChecked()
                else None
            ),
            "last_test_date": (
                qdate_to_py(self.de_test.date())
                if self.chk_test.isChecked()
                else None
            ),
            "test_interval_months": (
                self.sp_interval.value() if self.sp_interval.value() else None
            ),
            "notes": self.ed_notes.toPlainText().strip(),
        }
