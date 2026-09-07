from PySide6.QtCore import QObject, Signal

from .repositories import BoatRepository


class BoatWorker(QObject):
    finished = Signal(object)  # передаём результат
    error = Signal(str)

    def run(self):
        try:
            data = BoatRepository.get_all()
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))
