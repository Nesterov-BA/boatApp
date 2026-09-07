from decimal import InvalidContext

from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import LoaderCallableStatus
from sqlalchemy.types import Date

from .database import Base


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String)
    required_qty = Column(Integer)
    actual_qty = Column(Integer)
    expiry_date = Column(Date)
    last_test_date = Column(Date)
    status = Column(String)
