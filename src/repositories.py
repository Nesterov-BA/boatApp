from .database import SessionLocal
from .model import Item


class BoatRepository:
    @staticmethod
    def get_all():
        session = SessionLocal()
        try:
            return session.query(Item).all()
        finally:
            session.close()

    @staticmethod
    def add_item(
        name, location, required_qty, actual_qty, expiry_date, last_test_date, status
    ):
        session = SessionLocal()
        try:
            item = Item(
                name=name,
                location=location,
                required_qty=required_qty,
                actual_qty=actual_qty,
                expiry_date=expiry_date,
                last_test_date=last_test_date,
                status=status,
            )
            session.add(item)
            session.commit()
            return item
        finally:
            session.close()
