"""Общие помощники интерфейса: цвета статусов, даты, мелкие утилиты."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor

from . import logic

# Цвета оформления статусов (фон, текст) для строк таблицы имущества.
STATUS_COLORS: dict[str, tuple[str, str]] = {
    logic.ST_OK: ("#e6f4ea", "#0b5d1e"),
    logic.ST_SHORTAGE: ("#fff4e0", "#8a5300"),
    logic.ST_EXPIRED: ("#fde8e8", "#a50e0e"),
    logic.ST_EXPIRY_SOON: ("#fff4e0", "#8a5300"),
    logic.ST_TEST_OVERDUE: ("#fbe4e6", "#b0252e"),
    logic.ST_TEST_SOON: ("#fff8e1", "#92600a"),
}

DEFAULT_STATUS_COLOR = ("#ffffff", "#000000")


def status_colors(code: str) -> tuple[str, str]:
    return STATUS_COLORS.get(code, DEFAULT_STATUS_COLOR)


def status_hint(item) -> str:
    """Расширенная подсказка по статусам позиции для всплывающей подсказки."""
    today = date.today()
    parts: list[str] = []
    if item.expiry_date is not None:
        dl = logic.days_left(item.expiry_date, today)
        parts.append(
            f"Срок годности: {item.expiry_date:%d.%m.%Y}"
            + (f" (через {dl} дн.)" if dl is not None and dl >= 0 else " (истёк)")
        )
    nxt = logic.next_test_date(item)
    if nxt is not None:
        dl = logic.days_left(nxt, today)
        parts.append(
            f"Следующее освидетельствование: {nxt:%d.%m.%Y}"
            + (f" (через {dl} дн.)" if dl is not None and dl >= 0 else " (просрочено)")
        )
    if (item.actual_qty or 0) < (item.required_qty or 0):
        parts.append(
            f"Дефицит: требуется {item.required_qty}, фактически {item.actual_qty}"
        )
    return "\n".join(parts) if parts else "Отклонений не выявлено."


# --------------------------------------------------------------------------
# Даты
# --------------------------------------------------------------------------


def py_to_qdate(d: date | None) -> QDate:
    if d is None:
        return QDate.currentDate()
    return QDate(d.year, d.month, d.day)


def qdate_to_py(qd: QDate) -> date | None:
    if qd.isValid():
        return date(qd.year(), qd.month(), qd.day())
    return None


def fmt_date(d: date | None) -> str:
    if d is None:
        return "—"
    return f"{d:%d.%m.%Y}"
