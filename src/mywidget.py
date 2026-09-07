from PySide6.QtCore import QThread
from PySide6.QtWidgets import QListWidget, QVBoxLayout, QWidget

from .workers import BoatWorker


class BoatListWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)

        self.load_data()

    def load_data(self):
        # Создаём поток и воркер
        self.thread = (
            QThread()
        )  # теперь Pyright не ругается, если добавить аннотацию выше
        self.worker = BoatWorker()
        self.worker.moveToThread(self.thread)

        # Подключаем сигналы
        self.thread.started.connect(self.worker.run)  # было start → started
        self.worker.finished.connect(self.on_data_ready)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.error.connect(self.on_error)

        self.thread.start()  # запускаем поток

    def on_data_ready(self, boats):
        self.list.clear()
        for boat in boats:
            self.list.addItem(f"{boat.name} ({boat.length} m) - {boat.owner}")

    def on_error(self, msg):
        self.list.addItem(f"Ошибка: {msg}")
