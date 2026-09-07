"""Формирование акта осмотра и вывод его на печать / в PDF / в HTML-файл.

HTML-разметка самодостаточна (встроенные стили) и годится и для предпросмотра
в интерфейсе, и для печати на принтере, и для сохранения в PDF средствами Qt —
без дополнительных зависимостей.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from . import logic
from .models import Inspection


# --------------------------------------------------------------------------
# HTML акта
# --------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
         font-size: 11pt; color: #000; }}
  h1 {{ font-size: 16pt; text-align: center; margin: 0 0 4px 0; }}
  h2 {{ font-size: 13pt; text-align: center; margin: 0 0 18px 0;
        font-weight: normal; }}
  .meta {{ margin-bottom: 12px; }}
  .meta p {{ margin: 2px 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  th, td {{ border: 1px solid #333; padding: 4px 6px; vertical-align: top;
            font-size: 9.5pt; }}
  th {{ background: #eee; text-align: left; }}
  .n  {{ text-align: right; }}
  .result {{ margin-top: 12px; font-weight: bold; }}
  .sign {{ margin-top: 40px; }}
  .sign p {{ margin: 14px 0; }}
  .note {{ color: #555; font-size: 9pt; }}
</style>
</head>
<body>
<h1>АКТ ОСМОТРА (ПРОВЕРКИ)</h1>
<h2>аварийно-спасательного имущества судна</h2>

<div class="meta">
<p><b>№ {number}</b> &nbsp; от «__» __________ {year} г.</p>
<p><b>Судно:</b> {ship}</p>
<p><b>Тип судна:</b> {ship_type}&nbsp;&nbsp;&nbsp;<b>Позывной:</b> {call_sign}
&nbsp;&nbsp;&nbsp;<b>Порт приписки:</b> {home_port}</p>
<p><b>Осмотр провёл:</b> {inspector}</p>
</div>

<p>В ходе осмотра проверены наличие, состояние, комплектность и сроки
годности/освидетельствования следующего имущества:</p>

<table>
<tr>
  <th style="width:3%">№</th>
  <th style="width:14%">Группа</th>
  <th style="width:26%">Наименование</th>
  <th style="width:16%">Место хранения</th>
  <th class="n" style="width:6%">Треб.</th>
  <th class="n" style="width:6%">Найдено</th>
  <th style="width:12%">Оценка</th>
  <th style="width:17%">Замечания</th>
</tr>
{rows}
</table>

<div class="result">Результат осмотра: {result}</div>

<div class="note">Оценка строк акта: «Годен» — соответствует требованиям;
«Замечание» — требует доукомплектования/обслуживания/замены в установленный
срок; «Не годен» — не соответствует, эксплуатация до устранения
недостатков запрещена.</div>

<div class="sign">
<p>Осмотр провёл: ______________________________ / {inspector} /</p>
<p>Капитан (судовладелец): ____________________ / ____________________ /</p>
<p class="note">Настоящий акт хранится на судне до следующего осмотра.</p>
</div>
</body>
</html>
"""

_ROW_HTML = (
    "<tr>"
    "<td class='n'>{idx}</td>"
    "<td>{category}</td>"
    "<td>{name}</td>"
    "<td>{location}</td>"
    "<td class='n'>{required}</td>"
    "<td class='n'>{found}</td>"
    "<td>{state}</td>"
    "<td>{comment}</td>"
    "</tr>"
)


def render_act_html(inspection: Inspection) -> str:
    """HTML-документ акта по объекту осмотра (с уже загруженными entries)."""
    rows: list[str] = []
    for i, entry in enumerate(inspection.entries, start=1):
        rows.append(
            _ROW_HTML.format(
                idx=i,
                category=escape(entry.item_category or ""),
                name=escape(entry.item_name or ""),
                location=escape(entry.item_location or ""),
                required=entry.required_qty if entry.required_qty is not None else "—",
                found=entry.found_qty if entry.found_qty is not None else "—",
                state=escape(logic.STATE_RU.get(entry.state, entry.state)),
                comment=escape(entry.comment or "—"),
            )
        )
    if not rows:
        rows.append(
            "<tr><td colspan='8'>Нет записей об осмотре имущества.</td></tr>"
        )

    ship = inspection.ship
    return _HTML_TEMPLATE.format(
        number=escape(inspection.number or "—"),
        year=inspection.date.year,
        ship=escape(ship.name if ship else "—"),
        ship_type=escape((ship.ship_type if ship else "") or "—"),
        call_sign=escape((ship.call_sign if ship else "") or "—"),
        home_port=escape((ship.home_port if ship else "") or "—"),
        inspector=escape(inspection.inspector or "—"),
        rows="\n".join(rows),
        result=escape(logic.RESULT_RU.get(inspection.result, inspection.result)),
    )


def load_inspection(session, inspection_id: int) -> Inspection | None:
    """Загружает акт с судном и строками за один запрос."""
    from sqlalchemy.orm import joinedload

    return (
        session.query(Inspection)
        .options(
            joinedload(Inspection.ship),
            joinedload(Inspection.entries),
        )
        .filter(Inspection.id == inspection_id)
        .first()
    )


# --------------------------------------------------------------------------
# Печать и PDF (PySide6)
# --------------------------------------------------------------------------


def _make_printer():
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(
        QMarginsF(15, 12, 15, 12), QPageLayout.Unit.Millimeter
    )
    return printer


def _render_html(html: str, printer) -> None:
    from PySide6.QtGui import QTextDocument

    doc = QTextDocument()
    doc.setHtml(html)
    doc.print_(printer)
    doc.deleteLater()


def print_act_html(html: str, parent=None) -> bool:
    """Диалог печати. Возвращает True, если пользователь отправил на печать."""
    from PySide6.QtWidgets import QPrintDialog

    printer = _make_printer()
    dialog = QPrintDialog(printer, parent)
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return False
    _render_html(html, printer)
    return True


def save_act_pdf(html: str, filename: str | Path, parent=None) -> bool:
    """Сохраняет акт в PDF-файл. Возвращает True при успехе."""
    from PySide6.QtPrintSupport import QPrinter

    printer = _make_printer()
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(filename))
    _render_html(html, printer)
    return Path(filename).stat().st_size > 0


def save_act_html(html: str, filename: str | Path) -> None:
    """Сохраняет HTML-копию акта."""
    Path(filename).write_text(html, encoding="utf-8")
