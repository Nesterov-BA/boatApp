"""Модели данных: судно, имущество, акт осмотра и строки акта.

Схема хранит аварийно-спасательное имущество каждого судна и историю его
проверок (акты осмотра). Каждая строка акта — «снимок» позиции имущества на
момент проверки, поэтому акт не меняется при последующем редактировании
карточки имущества.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class Ship(Base):
    """Судно, на котором числится аварийно-спасательное имущество."""

    __tablename__ = "ships"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    ship_type = Column(String(100), default="", nullable=False)
    call_sign = Column(String(50), default="", nullable=False)
    home_port = Column(String(100), default="", nullable=False)
    notes = Column(Text, default="", nullable=False)

    items = relationship(
        "EquipmentItem",
        back_populates="ship",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EquipmentItem.category, EquipmentItem.name",
    )
    inspections = relationship(
        "Inspection",
        back_populates="ship",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Inspection.date.desc(), Inspection.id.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ship {self.id} {self.name!r}>"


class EquipmentItem(Base):
    """Позиция аварийно-спасательного имущества на судне."""

    __tablename__ = "equipment_items"

    id = Column(Integer, primary_key=True)
    ship_id = Column(
        Integer, ForeignKey("ships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    location = Column(String(200), default="", nullable=False)
    unit = Column(String(50), default="шт.", nullable=False)
    required_qty = Column(Integer, default=1, nullable=False)
    actual_qty = Column(Integer, default=0, nullable=False)
    expiry_date = Column(Date, nullable=True)  # срок годности / замены
    last_test_date = Column(Date, nullable=True)  # последнее освидетельствование
    test_interval_months = Column(Integer, nullable=True)  # периодичность, месяцев
    status = Column(String(30), default="ok", nullable=False)  # автоматический
    notes = Column(Text, default="", nullable=False)

    ship = relationship("Ship", back_populates="items")
    entries = relationship(
        "InspectionEntry",
        back_populates="item",
        passive_deletes=True,  # при удалении позиции строки актов сохраняются
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Item {self.id} {self.name!r}>"


class Inspection(Base):
    """Акт осмотра (проверки) аварийно-спасательного имущества судна."""

    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True)
    ship_id = Column(
        Integer, ForeignKey("ships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number = Column(String(60), default="", nullable=False)
    date = Column(Date, nullable=False)
    inspector = Column(String(200), nullable=False)
    result = Column(String(20), default="ok", nullable=False)  # ok | notes | failed
    summary = Column(Text, default="", nullable=False)

    ship = relationship("Ship", back_populates="inspections")
    entries = relationship(
        "InspectionEntry",
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InspectionEntry.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Inspection {self.id} {self.number!r}>"


class InspectionEntry(Base):
    """Строка акта осмотра — результат проверки одной позиции имущества."""

    __tablename__ = "inspection_entries"

    id = Column(Integer, primary_key=True)
    inspection_id = Column(
        Integer,
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(
        Integer,
        ForeignKey("equipment_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # «Снимок» на момент проверки, чтобы акт оставался неизменным:
    item_name = Column(String(200), default="", nullable=False)
    item_location = Column(String(200), default="", nullable=False)
    item_category = Column(String(100), default="", nullable=False)
    required_qty = Column(Integer, nullable=False)
    found_qty = Column(Integer, nullable=False)
    state = Column(String(20), default="ok", nullable=False)  # ok | note | fail
    comment = Column(Text, default="", nullable=False)

    inspection = relationship("Inspection", back_populates="entries")
    item = relationship("EquipmentItem", back_populates="entries")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Entry {self.id} {self.item_name!r}>"
