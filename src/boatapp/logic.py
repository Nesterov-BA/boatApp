"""Бизнес-логика: статусы имущества, расчёт сроков, типовой перечень АСИ,
формирование акта осмотра и сводная статистика."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable

from .db import SessionLocal
from .models import EquipmentItem, Inspection, InspectionEntry, Ship

# --------------------------------------------------------------------------
# Константы статусов и их русские названия
# --------------------------------------------------------------------------

ST_OK = "ok"
ST_SHORTAGE = "shortage"  # фактически меньше требуемого
ST_EXPIRED = "expired"  # истёк срок годности
ST_EXPIRY_SOON = "expiry_soon"  # срок годности истекает в ближайшие дни
ST_TEST_OVERDUE = "test_overdue"  # просрочено освидетельствование
ST_TEST_SOON = "test_soon"  # освидетельствование подходит к сроку

STATUS_RU: dict[str, str] = {
    ST_OK: "В норме",
    ST_SHORTAGE: "Дефицит",
    ST_EXPIRED: "Срок годности истёк",
    ST_EXPIRY_SOON: "Срок годности скоро",
    ST_TEST_OVERDUE: "Просрочено освидетельствование",
    ST_TEST_SOON: "Освидетельствование скоро",
}

SOON_DAYS = 30  # порог «скоро» для предупреждений

STATE_OK = "ok"
STATE_NOTE = "note"
STATE_FAIL = "fail"

STATE_RU: dict[str, str] = {
    STATE_OK: "Годен",
    STATE_NOTE: "Замечание",
    STATE_FAIL: "Не годен",
}

RESULT_OK = "ok"
RESULT_NOTES = "notes"
RESULT_FAILED = "failed"

RESULT_RU: dict[str, str] = {
    RESULT_OK: "Соответствует (без замечаний)",
    RESULT_NOTES: "Соответствует с замечаниями",
    RESULT_FAILED: "Не соответствует требованиям",
}

# Порядок приоритета при выборе «главного» статуса строки таблицы:
_STATUS_PRIORITY: list[str] = [
    ST_EXPIRED,
    ST_TEST_OVERDUE,
    ST_SHORTAGE,
    ST_EXPIRY_SOON,
    ST_TEST_SOON,
    ST_OK,
]

# --------------------------------------------------------------------------
# Работа с датами
# --------------------------------------------------------------------------


def add_months(base: date, months: int | None) -> date | None:
    """Возвращает дату через *months* месяцев (с учётом длины месяца)."""
    if base is None or not months:
        return None
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, monthrange(year, month)[1])
    return date(year, month, day)


def next_test_date(item: EquipmentItem) -> date | None:
    """Дата следующего освидетельствования позиции (или None)."""
    interval = item.test_interval_months
    if item.last_test_date is None or not interval:
        return None
    return add_months(item.last_test_date, interval)


def days_left(target: date | None, today: date) -> int | None:
    if target is None:
        return None
    return (target - today).days


# --------------------------------------------------------------------------
# Статус позиции имущества
# --------------------------------------------------------------------------


def item_flags(item: EquipmentItem, today: date | None = None) -> list[str]:
    """Все отклонения позиции (от худшего к лучшему). Пусто — всё в норме."""
    today = today or date.today()
    flags: list[str] = []
    if item.expiry_date is not None:
        dl = days_left(item.expiry_date, today)
        if dl is not None and dl < 0:
            flags.append(ST_EXPIRED)
        elif dl is not None and dl <= SOON_DAYS:
            flags.append(ST_EXPIRY_SOON)
    nxt = next_test_date(item)
    if nxt is not None:
        dl = days_left(nxt, today)
        if dl < 0:
            flags.append(ST_TEST_OVERDUE)
        elif dl <= SOON_DAYS:
            flags.append(ST_TEST_SOON)
    if (item.actual_qty or 0) < (item.required_qty or 0):
        flags.append(ST_SHORTAGE)
    return flags


def compute_status(item: EquipmentItem, today: date | None = None) -> str:
    """Основной статус позиции."""
    flags = item_flags(item, today)
    if not flags:
        return ST_OK
    for code in _STATUS_PRIORITY:
        if code in flags:
            return code
    return ST_OK


def refresh_item_status(item: EquipmentItem, today: date | None = None) -> str:
    """Пересчитывает и сохраняет статус позиции в памяти (без коммита)."""
    code = compute_status(item, today)
    item.status = code
    return code


def refresh_ship_statuses(ship_id: int) -> int:
    """Пересчитывает статусы всех позиций судна в БД. Возвращает их число."""
    session = SessionLocal()
    try:
        items = (
            session.query(EquipmentItem)
            .filter(EquipmentItem.ship_id == ship_id)
            .all()
        )
        for it in items:
            refresh_item_status(it)
        session.commit()
        return len(items)
    finally:
        session.close()


# --------------------------------------------------------------------------
# Типовой перечень аварийно-спасательного имущества
# --------------------------------------------------------------------------

CATEGORIES: list[str] = [
    "Средства индивидуального спасения",
    "Коллективные средства спасения",
    "Противопожарное имущество",
    "Аварийное имущество",
    "Средства связи и сигнализации",
    "Пиротехнические средства",
    "Медицинское имущество",
]

# Типовой набор для примера (маломерное/прогулочное судно). Все позиции
# можно отредактировать или удалить после добавления на судно.
PRESET_ITEMS: list[dict] = [
    {
        "category": "Средства индивидуального спасения",
        "name": "Спасательный жилет",
        "location": "Под сиденьями / в каюте, по числу людей на борту",
        "unit": "шт.",
        "qty": 6,
        "interval_months": 12,
        "note": "Осмотр: целостность, наполняемость, светоотражатели.",
    },
    {
        "category": "Средства индивидуального спасения",
        "name": "Спасательный круг",
        "location": "Кокпит, в легкодоступном месте",
        "unit": "шт.",
        "qty": 2,
        "interval_months": 12,
        "note": "Осмотр: леер, светоотражающие полосы.",
    },
    {
        "category": "Средства индивидуального спасения",
        "name": "Конец спасательный (линь с поплавком)",
        "location": "У спасательного круга",
        "unit": "шт.",
        "qty": 2,
        "interval_months": 12,
        "note": "Длина не менее 30 м, плавучесть поплавка.",
    },
    {
        "category": "Средства индивидуального спасения",
        "name": "Одеяло спасательное",
        "location": "Аптечка / рундук кокпита",
        "unit": "шт.",
        "qty": 2,
        "interval_months": None,
        "note": "Влагозащитная упаковка.",
    },
    {
        "category": "Коллективные средства спасения",
        "name": "Спасательный плот надувной",
        "location": "На палубе, у места спуска",
        "unit": "компл.",
        "qty": 1,
        "interval_months": 12,
        "note": "Освидетельствование на станции, перезарядка баллона CO2.",
    },
    {
        "category": "Коллективные средства спасения",
        "name": "Аварийный запас плота (рацион, вода, снабжение)",
        "location": "Внутри контейнера плота",
        "unit": "компл.",
        "qty": 1,
        "interval_months": 12,
        "note": "Срок годности продуктов — по маркировке контейнера.",
    },
    {
        "category": "Противопожарное имущество",
        "name": "Огнетушитель порошковый ОП-4",
        "location": "У входа в каюту/камбуз",
        "unit": "шт.",
        "qty": 2,
        "interval_months": 12,
        "note": "Контроль давления/веса, перезарядка по сроку.",
    },
    {
        "category": "Противопожарное имущество",
        "name": "Огнетушитель углекислотный ОУ-3",
        "location": "У двигателя / электрощита",
        "unit": "шт.",
        "qty": 1,
        "interval_months": 12,
        "note": "Контроль массы заряда.",
    },
    {
        "category": "Противопожарное имущество",
        "name": "Одеяло противопожарное (стеклоткань)",
        "location": "Камбуз",
        "unit": "шт.",
        "qty": 1,
        "interval_months": 12,
        "note": "Осмотр на повреждения.",
    },
    {
        "category": "Аварийное имущество",
        "name": "Водоотливной насос ручной",
        "location": "Рундук кокпита",
        "unit": "шт.",
        "qty": 1,
        "interval_months": 12,
        "note": "Проверка работоспособности.",
    },
    {
        "category": "Аварийное имущество",
        "name": "Комплект аварийного инструмента (топор, ломик)",
        "location": "В рубке, легкодоступно",
        "unit": "компл.",
        "qty": 1,
        "interval_months": None,
        "note": "Комплектность по описи.",
    },
    {
        "category": "Аварийное имущество",
        "name": "Комплект пластыря аварийного (пробки, заглушки)",
        "location": "Рундук кокпита",
        "unit": "компл.",
        "qty": 1,
        "interval_months": None,
        "note": "Комплектность по описи.",
    },
    {
        "category": "Средства связи и сигнализации",
        "name": "Радиостанция УКВ носимая",
        "location": "Рубка",
        "unit": "шт.",
        "qty": 1,
        "interval_months": 6,
        "note": "Проверка заряда АКБ и работоспособности.",
    },
    {
        "category": "Средства связи и сигнализации",
        "name": "Аварийный радиобуй (АРБ/EPIRB 406 МГц)",
        "location": "На верхней палубе, на кронштейне",
        "unit": "шт.",
        "qty": 1,
        "interval_months": 12,
        "note": "Тест-режим, срок службы батареи по инструкции.",
    },
    {
        "category": "Пиротехнические средства",
        "name": "Фальшфейер красный",
        "location": "Водонепроницаемый контейнер в рубке",
        "unit": "шт.",
        "qty": 4,
        "interval_months": 6,
        "note": "Срок годности — по маркировке (обычно 3 года).",
    },
    {
        "category": "Пиротехнические средства",
        "name": "Ракета сигнальная с парашютом",
        "location": "Водонепроницаемый контейнер в рубке",
        "unit": "шт.",
        "qty": 4,
        "interval_months": 6,
        "note": "Срок годности — по маркировке (обычно 3 года).",
    },
    {
        "category": "Пиротехнические средства",
        "name": "Дымовая шашка плавучая (оранжевый дым)",
        "location": "Водонепроницаемый контейнер в рубке",
        "unit": "шт.",
        "qty": 2,
        "interval_months": 6,
        "note": "Срок годности — по маркировке (обычно 3 года).",
    },
    {
        "category": "Медицинское имущество",
        "name": "Аптечка первой помощи",
        "location": "Рубка / каюта",
        "unit": "компл.",
        "qty": 1,
        "interval_months": 12,
        "note": "Пополнение, контроль сроков медикаментов.",
    },
]


def add_preset_items(session, ship_id: int) -> int:
    """Добавляет на судно типовой перечень АСИ. Возвращает число позиций."""
    added = 0
    for spec in PRESET_ITEMS:
        item = EquipmentItem(
            ship_id=ship_id,
            category=spec["category"],
            name=spec["name"],
            location=spec["location"],
            unit=spec.get("unit", "шт."),
            required_qty=spec.get("qty", 1),
            actual_qty=spec.get("qty", 1),
            test_interval_months=spec.get("interval_months"),
            notes=spec.get("note", ""),
        )
        refresh_item_status(item)
        session.add(item)
        added += 1
    return added


# --------------------------------------------------------------------------
# Акты осмотра
# --------------------------------------------------------------------------


def build_check_rows(ship_id: int) -> list[EquipmentItem]:
    """Позиции судна для формы осмотра (в порядке перечня)."""
    session = SessionLocal()
    try:
        items = (
            session.query(EquipmentItem)
            .filter(EquipmentItem.ship_id == ship_id)
            .order_by(EquipmentItem.category, EquipmentItem.name)
            .all()
        )
        return list(items)
    finally:
        session.close()


def suggested_state(item: EquipmentItem, today: date | None = None) -> str:
    """Рекомендуемая оценка позиции на осмотре по её текущему статусу."""
    today = today or date.today()
    flags = item_flags(item, today)
    if ST_EXPIRED in flags:
        return STATE_FAIL
    if ST_TEST_OVERDUE in flags or ST_SHORTAGE in flags:
        return STATE_NOTE
    return STATE_OK


def aggregate_result(entries: Iterable[InspectionEntry]) -> str:
    """Итог акта по оценкам строк."""
    states = [e.state for e in entries]
    if not states:
        return RESULT_OK
    if STATE_FAIL in states:
        return RESULT_FAILED
    if STATE_NOTE in states:
        return RESULT_NOTES
    return RESULT_OK


def make_number(ship: Ship, check_date: date, existing: int) -> str:
    """Номер акта вида «АСИ-2025-001» (уникальность гарантируется id)."""
    # id становится известен только после flush, поэтому номер формируем
    # с порядковым номером по дате; при совпадении добавляем суффикс.
    return f"АСИ-{check_date:%Y}-{existing:03d}"


def perform_inspection(
    *,
    ship_id: int,
    check_date: date,
    inspector: str,
    results: list[dict],
    summary: str = "",
) -> Inspection:
    """Выполняет осмотр: обновляет имущество и создаёт акт.

    results — список словарей вида
      {item_id, found_qty, state, comment, name, location, category,
       required_qty}
    где поля name/location/category/required_qty — «снимок» из формы осмотра
    для хранения в акте. Позиции со state None пропускаются (не проверялись).
    """
    session = SessionLocal()
    try:
        ship = session.get(Ship, ship_id)
        if ship is None:
            raise ValueError("Судно не найдено")

        inspection = Inspection(
            ship_id=ship_id,
            date=check_date,
            inspector=inspector.strip(),
            summary=summary,
        )
        session.add(inspection)
        session.flush()  # получаем inspection.id

        prev = (
            session.query(Inspection)
            .filter(
                Inspection.ship_id == ship_id,
                Inspection.id != inspection.id,
            )
            .count()
        )
        inspection.number = make_number(ship, check_date, prev + 1)

        entries: list[InspectionEntry] = []
        for row in results:
            item_id = row["item_id"]
            state = row.get("state")
            if state is None or state not in (STATE_OK, STATE_NOTE, STATE_FAIL):
                continue
            item = session.get(EquipmentItem, item_id)
            if item is None:
                continue  # позиция удалена во время редактирования формы
            found_qty = int(row.get("found_qty", item.actual_qty or 0))
            entry = InspectionEntry(
                inspection_id=inspection.id,
                item_id=item_id,
                item_name=row.get("name") or item.name,
                item_location=row.get("location") or item.location or "",
                item_category=row.get("category") or item.category or "",
                required_qty=item.required_qty or 0,
                found_qty=found_qty,
                state=state,
                comment=(row.get("comment") or "").strip(),
            )
            session.add(entry)
            entries.append(entry)

            # Обновляем карточку имущества по результатам осмотра:
            item.actual_qty = found_qty
            item.last_test_date = check_date
            refresh_item_status(item, check_date)

        inspection.result = aggregate_result(entries)
        session.commit()
        session.refresh(inspection)
        return inspection
    finally:
        session.close()


# --------------------------------------------------------------------------
# Сводная статистика
# --------------------------------------------------------------------------


def ship_summary(ship_id: int) -> dict:
    """Подсчёт позиций судна по статусам."""
    counts = {code: 0 for code in _STATUS_PRIORITY}
    session = SessionLocal()
    try:
        items = (
            session.query(EquipmentItem)
            .filter(EquipmentItem.ship_id == ship_id)
            .all()
        )
        for it in items:
            counts[it.status] = counts.get(it.status, 0) + 1
    finally:
        session.close()
    return counts


def ships_with_totals() -> list[dict]:
    """Список судов с количеством имущества и проблемных позиций."""
    session = SessionLocal()
    try:
        ships = session.query(Ship).order_by(Ship.name).all()
        out = []
        for ship in ships:
            counts = ship_summary(ship.id)
            out.append(
                {
                    "ship": ship,
                    "total": sum(counts.values()),
                    "shortage": counts.get(ST_SHORTAGE, 0),
                    "expired": counts.get(ST_EXPIRED, 0),
                    "test_overdue": counts.get(ST_TEST_OVERDUE, 0),
                    "soon": counts.get(ST_EXPIRY_SOON, 0)
                    + counts.get(ST_TEST_SOON, 0),
                }
            )
        return out
    finally:
        session.close()


def create_demo_data() -> tuple[int, int]:
    """Создаёт демонстрационные данные: судно с типовым имуществом,
    намеренными дефектами и примером акта осмотра.

    Возвращает (ship_id, inspection_id).
    """
    from datetime import timedelta

    session = SessionLocal()
    try:
        ship = Ship(
            name="Нептун",
            ship_type="Маломерное судно",
            call_sign="МР-0001-А",
            home_port="Санкт-Петербург",
            notes="Демонстрационные данные. Можно отредактировать или удалить "
            "судно и вести свои записи.",
        )
        session.add(ship)
        session.flush()
        add_preset_items(session, ship.id)
        session.flush()

        today = date.today()
        by_name: dict[str, EquipmentItem] = {}
        for it in session.query(EquipmentItem).filter_by(ship_id=ship.id).all():
            by_name[it.name] = it

        def tweak(name: str, **kw) -> None:
            item = by_name.get(name)
            if item is not None:
                for key, value in kw.items():
                    setattr(item, key, value)

        # Намеренные отклонения для наглядности статусов:
        tweak("Спасательный жилет", actual_qty=4)  # дефицит (6 требуется)
        tweak("Аварийный радиобуй (АРБ/EPIRB 406 МГц)",
              last_test_date=today - timedelta(days=400))  # просрочено освид.
        tweak("Фальшфейер красный",
              expiry_date=today - timedelta(days=200))  # истёк срок годности
        tweak("Огнетушитель порошковый ОП-4",
              expiry_date=today + timedelta(days=20),
              last_test_date=today - timedelta(days=370))
        tweak("Дымовая шашка плавучая (оранжевый дым)",
              expiry_date=today + timedelta(days=12))

        for it in session.query(EquipmentItem).filter_by(ship_id=ship.id).all():
            refresh_item_status(it)

        # Пример акта осмотра 40 дней назад
        act_date = today - timedelta(days=40)
        inspector = "Капитан Иванов И. И."
        inspection = Inspection(
            ship_id=ship.id,
            date=act_date,
            inspector=inspector,
        )
        session.add(inspection)
        session.flush()
        prev = (
            session.query(Inspection)
            .filter(
                Inspection.ship_id == ship.id,
                Inspection.id != inspection.id,
            )
            .count()
        )
        inspection.number = make_number(ship, act_date, prev + 1)

        states: dict[str, tuple[str, str]] = {
            "Спасательный жилет": (STATE_NOTE, "Требуется доукомплектование "
                                  "(6 по списку, фактически 4)."),
            "Аварийный радиобуй (АРБ/EPIRB 406 МГц)": (
                STATE_NOTE, "Просрочено освидетельствование — направить "
                "на проверку."),
            "Огнетушитель порошковый ОП-4": (
                STATE_NOTE, "Контроль заряда, уточнить дату перезарядки."),
        }
        entries: list[InspectionEntry] = []
        for it in session.query(EquipmentItem).filter_by(ship_id=ship.id).all():
            state, comment = states.get(it.name, (STATE_OK, ""))
            entries.append(
                InspectionEntry(
                    inspection_id=inspection.id,
                    item_id=it.id,
                    item_name=it.name,
                    item_location=it.location or "",
                    item_category=it.category or "",
                    required_qty=it.required_qty or 0,
                    found_qty=it.actual_qty or 0,
                    state=state,
                    comment=comment,
                )
            )
        inspection.result = aggregate_result(entries)
        inspection.summary = (
            "В целом имущество соответствует требованиям. Отмеченные "
            "замечания устранить до следующего осмотра."
        )
        session.add_all(entries)
        session.commit()
        session.refresh(ship)
        return ship.id, inspection.id
    finally:
        session.close()
