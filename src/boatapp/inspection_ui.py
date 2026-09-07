"""Интерфейс осмотра: форма новой проверки, выбор акта, предпросмотр/печать."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import logic, reports
from .db import SessionLocal
from .models import Inspection
from .ui_common import fmt_date, qdate_to_py

_DATE_FORMAT = "dd.MM.yyyy"
_STATE_LABELS = [logic.STATE_RU[logic.STATE_OK],
                 logic.STATE_RU[logic.STATE_NOTE],
                 logic.STATE_RU[logic.STATE_FAIL]]


class InspectionDialog(QDialog):
    """Новый осмотр (проверка) имущества выбранного судна."""

    def __init__(self, parent: QWidget | None, ship_name: str, ship_id: int):
        super().__init__(parent)
        self._ship_id = ship_id
        self._items = logic.build_check_rows(ship_id)

        self.setWindowTitle(f"Осмотр имущества — {ship_name}")
        self.resize(1150, 620)

        settings = QSettings()
        last_inspector = settings.value("inspection/last_inspector", "")

        # Шапка
        head = QHBoxLayout()
        head.addWidget(QLabel("Дата осмотра:"))
        self.de_date = QDateEdit()
        self.de_date.setCalendarPopup(True)
        self.de_date.setDisplayFormat(_DATE_FORMAT)
        self.de_date.setDate(QDate.currentDate())
        head.addWidget(self.de_date)
        head.addSpacing(12)
        head.addWidget(QLabel("Осмотр провёл:"))
        self.ed_inspector = QLineEdit(str(last_inspector or ""))
        self.ed_inspector.setPlaceholderText("ФИО / должность")
        self.ed_inspector.setMinimumWidth(240)
        head.addWidget(self.ed_inspector, 1)

        # Таблица позиций
        headers = [
            "Проверено",
            "Оценка",
            "Группа",
            "Наименование",
            "Место хранения",
            "Треб.",
            "Найдено",
            "Срок годности",
            "Посл. освид.",
            "След. освид.",
            "Замечания / комментарий",
        ]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._populate()

        self.lbl_count = QLabel("")
        self._update_count_label()

        btn_all = QPushButton("Отметить все")
        btn_none = QPushButton("Снять все")
        btn_all.clicked.connect(lambda: self._set_checked_all(True))
        btn_none.clicked.connect(lambda: self._set_checked_all(False))

        row_actions = QHBoxLayout()
        row_actions.addWidget(btn_all)
        row_actions.addWidget(btn_none)
        row_actions.addStretch(1)
        row_actions.addWidget(self.lbl_count)

        buttons = QDialogButtonBox()
        b_save = buttons.addButton(
            "Сохранить акт", QDialogButtonBox.ButtonRole.AcceptRole
        )
        b_cancel = buttons.addButton(
            "Отмена", QDialogButtonBox.ButtonRole.RejectRole
        )
        b_save.clicked.connect(self._on_save)
        b_cancel.clicked.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(head)
        lay.addWidget(self.table)
        lay.addLayout(row_actions)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------

    def _populate(self) -> None:
        self.table.setRowCount(0)
        for item in self._items:
            row = self.table.rowCount()
            self.table.insertRow(row)

            chk = QCheckBox()
            chk.setChecked(True)
            chk.toggled.connect(self._update_count_label)
            self.table.setCellWidget(row, 0, chk)

            cb_state = QComboBox()
            cb_state.addItems(_STATE_LABELS)
            suggested = logic.suggested_state(item)
            cb_state.setCurrentText(logic.STATE_RU[suggested])
            self.table.setCellWidget(row, 1, cb_state)

            texts = [
                item.category or "",
                item.name,
                item.location or "",
                str(item.required_qty or 0),
                "",
                fmt_date(item.expiry_date),
                fmt_date(item.last_test_date),
                fmt_date(logic.next_test_date(item)),
            ]
            for col, text in enumerate(texts):
                cell = QTableWidgetItem(text)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col + 2, cell)

            sp_found = QSpinBox()
            sp_found.setRange(0, 9999)
            sp_found.setValue(item.actual_qty or 0)
            self.table.setCellWidget(row, 6, sp_found)

            ed_comment = QLineEdit()
            self.table.setCellWidget(row, 10, ed_comment)

            # Подсветка строки по текущему статусу позиции
            bg, fg = _row_colors(item)
            for col in range(2, 11):
                cell = self.table.item(row, col)
                if cell is not None:
                    cell.setBackground(QColor(bg))
                    cell.setForeground(QColor(fg))

        self.table.resizeColumnsToContents()

    def _update_count_label(self, *_args) -> None:
        total = self.table.rowCount()
        checked = 0
        for row in range(total):
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, QCheckBox) and chk.isChecked():
                checked += 1
        self.lbl_count.setText(f"Будет проверено позиций: {checked} из {total}")

    def _set_checked_all(self, value: bool) -> None:
        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, QCheckBox):
                chk.setChecked(value)

    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        inspector = self.ed_inspector.text().strip()
        if not inspector:
            QMessageBox.warning(
                self, "Осмотр", "Укажите, кто проводит осмотр (ФИО/должность)."
            )
            self.ed_inspector.setFocus()
            return

        results: list[dict] = []
        for row, item in enumerate(self._items):
            chk = self.table.cellWidget(row, 0)
            if not (isinstance(chk, QCheckBox) and chk.isChecked()):
                continue
            state_combo = self.table.cellWidget(row, 1)
            state_label = state_combo.currentText()
            state = next(
                k for k, v in logic.STATE_RU.items() if v == state_label
            )
            spin = self.table.cellWidget(row, 6)
            found = spin.value() if isinstance(spin, QSpinBox) else item.actual_qty
            ed = self.table.cellWidget(row, 10)
            comment = ed.text() if isinstance(ed, QLineEdit) else ""
            results.append(
                {
                    "item_id": item.id,
                    "found_qty": int(found or 0),
                    "state": state,
                    "comment": comment,
                    "name": item.name,
                    "location": item.location or "",
                    "category": item.category or "",
                }
            )

        if not results:
            QMessageBox.warning(
                self,
                "Осмотр",
                "Не отмечено ни одной позиции для проверки.\n"
                "Отметьте позиции колонкой «Проверено» или отмените осмотр.",
            )
            return

        check_date = qdate_to_py(self.de_date.date()) or date.today()

        QSettings().setValue("inspection/last_inspector", inspector)

        try:
            inspection = logic.perform_inspection(
                ship_id=self._ship_id,
                check_date=check_date,
                inspector=inspector,
                results=results,
            )
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self, "Осмотр", f"Не удалось сохранить акт:\n{exc}"
            )
            return

        preview = ActPreviewDialog(
            inspection_id=inspection.id,
            parent=self,
            auto_created=True,
        )
        preview.exec()
        self.accept()

    # ------------------------------------------------------------------


def _row_colors(item) -> tuple[str, str]:
    """Цвета фона/текста строки осмотра по текущему статусу позиции."""
    from .ui_common import status_colors

    return status_colors(item.status)


class ActPreviewDialog(QDialog):
    """Предпросмотр акта с печатью и сохранением в PDF/HTML."""

    def __init__(
        self,
        inspection_id: int,
        parent: QWidget | None = None,
        auto_created: bool = False,
    ):
        super().__init__(parent)
        self._inspection_id = inspection_id
        self._html = ""
        self.setWindowTitle("Акт осмотра — предпросмотр")
        self.resize(900, 700)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        # акт всегда «бумажный»: белый фон с чёрным текстом, независимо от темы
        self.browser.setStyleSheet(
            "QTextBrowser { background-color: #ffffff; color: #000000; }"
        )

        btn_pdf = QPushButton("Сохранить PDF…")
        btn_print = QPushButton("Печать…")
        btn_html = QPushButton("Сохранить HTML…")
        btn_close = QPushButton("Закрыть")
        btn_pdf.clicked.connect(self._save_pdf)
        btn_print.clicked.connect(self._print)
        btn_html.clicked.connect(self._save_html)
        btn_close.clicked.connect(self.accept)

        hint = QLabel(
            "Акт сформирован по данным осмотра."
            if auto_created
            else "Акт загружен из журнала проверок судна."
        )
        hint.setStyleSheet("color: #555;")

        btns = QHBoxLayout()
        btns.addWidget(btn_pdf)
        btns.addWidget(btn_print)
        btns.addWidget(btn_html)
        btns.addStretch(1)
        btns.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.browser)
        lay.addLayout(btns)

        self._load()

    # ------------------------------------------------------------------

    def _load(self) -> None:
        session = SessionLocal()
        try:
            inspection = reports.load_inspection(session, self._inspection_id)
            if inspection is None:
                QMessageBox.warning(
                    self, "Акт", "Акт не найден в базе данных."
                )
                self.accept()
                return
            self._html = reports.render_act_html(inspection)
        finally:
            session.close()
        self.browser.setHtml(self._html)

    def _default_dir(self) -> Path:
        project = Path(__file__).resolve().parent.parent.parent
        acts_dir = project / "Акты осмотра"
        acts_dir.mkdir(exist_ok=True)
        return acts_dir

    def _default_name(self) -> str:
        session = SessionLocal()
        try:
            inspection = reports.load_inspection(session, self._inspection_id)
            number = inspection.number if inspection else f"АСИ-{self._inspection_id}"
        finally:
            session.close()
        safe = "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in number
        )
        return f"{safe}.pdf"

    def _save_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить акт в PDF",
            str(self._default_dir() / self._default_name()),
            "PDF-файл (*.pdf)",
        )
        if not path:
            return
        try:
            reports.save_act_pdf(self._html, path, parent=self)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self, "PDF", f"Не удалось сохранить PDF:\n{exc}"
            )
            return
        QMessageBox.information(
            self, "PDF", f"Акт сохранён:\n{path}"
        )

    def _save_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить копию акта (HTML)",
            str(self._default_dir() / self._default_name().replace(".pdf", ".html")),
            "HTML (*.html)",
        )
        if not path:
            return
        try:
            reports.save_act_html(self._html, path)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "HTML", f"Ошибка сохранения:\n{exc}")
            return
        QMessageBox.information(self, "HTML", f"Акт сохранён:\n{path}")

    def _print(self) -> None:
        try:
            reports.print_act_html(self._html, parent=self)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Печать", f"Ошибка печати:\n{exc}")


class InspectionPickerDialog(QDialog):
    """Выбор акта осмотра судна из журнала для просмотра/печати."""

    def __init__(self, parent: QWidget | None, ship_name: str, ship_id: int):
        super().__init__(parent)
        self.setWindowTitle(f"Акты осмотра — {ship_name}")
        self.resize(640, 420)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda *_: self._open())

        btn_open = QPushButton("Открыть / распечатать")
        btn_del = QPushButton("Удалить акт")
        btn_close = QPushButton("Закрыть")
        btn_open.clicked.connect(self._open)
        btn_del.clicked.connect(self._delete)
        btn_close.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addWidget(btn_open)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        btns.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(self.list)
        lay.addLayout(btns)

        self._load(ship_id)

    # ------------------------------------------------------------------

    def _load(self, ship_id: int) -> None:
        session = SessionLocal()
        try:
            inspections = (
                session.query(Inspection)
                .filter(Inspection.ship_id == ship_id)
                .order_by(Inspection.date.desc(), Inspection.id.desc())
                .all()
            )
            for insp in inspections:
                label = (
                    f"{insp.number} · от {fmt_date(insp.date)} · "
                    f"{logic.RESULT_RU.get(insp.result, insp.result)} · "
                    f"инспектор: {insp.inspector}"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, insp.id)
                self.list.addItem(item)
        finally:
            session.close()
        if self.list.count() == 0:
            self.list.addItem(
                "Актов пока нет. Проведите осмотр кнопкой «Осмотр (акт)…»."
            )

    def _selected_id(self) -> int | None:
        row = self.list.currentRow()
        if row < 0:
            return None
        item = self.list.item(row)
        value = item.data(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, int) else None

    def _open(self) -> None:
        insp_id = self._selected_id()
        if insp_id is None:
            QMessageBox.information(
                self, "Акты осмотра", "Выберите акт из списка."
            )
            return
        dlg = ActPreviewDialog(insp_id, parent=self)
        dlg.exec()

    def _delete(self) -> None:
        insp_id = self._selected_id()
        if insp_id is None:
            QMessageBox.information(
                self, "Акты осмотра", "Выберите акт из списка."
            )
            return
        ret = QMessageBox.question(
            self,
            "Удаление акта",
            "Удалить выбранный акт осмотра?\n"
            "История проверок этого акта будет удалена безвозвратно.\n"
            "Карточки имущества при этом не изменятся.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        session = SessionLocal()
        try:
            insp = session.get(Inspection, insp_id)
            if insp is not None:
                session.delete(insp)
                session.commit()
        finally:
            session.close()
        self.accept()  # закрываем — главное окно само обновит журнал
