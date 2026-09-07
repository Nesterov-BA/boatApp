import sys

from PySide6.QtWidgets import QApplication, QWidget  # Add QWidget

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Create and show a window
    window = QWidget()
    window.setWindowTitle("My App")
    window.resize(400, 300)
    window.show()  # <-- This is what makes it visible!

    sys.exit(app.exec())
