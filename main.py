import sys

from PySide6.QtWidgets import QApplication, QWidget  # Add QWidget

from src.database import Base, engine
from src.model import Item
from src.mywidget import BoatListWidget

if __name__ == "__main__":
    Base.metadata.create_all(engine, checkfirst=True)
    app = QApplication(sys.argv)

    # Create and show a window
    window = BoatListWidget()
    window.setWindowTitle("My App")
    window.resize(400, 300)
    window.show()  # <-- This is what makes it visible!

    sys.exit(app.exec())
