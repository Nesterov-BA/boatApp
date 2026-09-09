"""Графический диалог настройки базы данных.

Показывается при первом запуске (если база ещё не настроена) и доступен из
меню «Настройки → База данных…». Позволяет выбрать локальную базу SQLite или
серверную (PostgreSQL / MySQL / MariaDB), проверить подключение, сохранить
настройки и сразу переключиться — без ввода команд в консоли.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import db

# (название для интерфейса, диалект SQLAlchemy, порт по умолчанию)
BACKENDS: list[tuple[str, str, int]] = [
    ("PostgreSQL", "postgresql+psycopg", 5432),
    ("MySQL", "mysql+pymysql", 3306),
    ("MariaDB", "mariadb+pymysql", 3306),
]

DRIVER_HINT = (
    "Если драйвер СУБД не установлен, появится понятное сообщение об ошибке. "
    "Установить драйвер нужно один раз:\n"
    "  uv sync --extra postgres   (PostgreSQL)\n"
    "  uv sync --extra mysql      (MySQL / MariaDB)"
)


def compose_server_url(backend_key: str, host: str, port: int,
                       database: str, user: str, password: str) -> str:
    """Собирает SQLAlchemy-URL серверной базы по полям формы."""
    dialect = next(d for _, d, _ in BACKENDS if d == backend_key)
    host = (host or "").strip()
    database = (database or "").strip()
    user = (user or "").strip()
    password = password or ""
    if not host or not database:
        raise ValueError("Укажите адрес сервера (host) и имя базы данных.")

    cred = quote(user)
    if password:
        cred += ":" + quote(password)
    url = f"{dialect}://{cred}@{host}:{int(port)}/{quote(database)}"
    if dialect in ("mysql+pymysql", "mariadb+pymysql"):
        url += "?charset=utf8mb4"
    return url


class DbSetupDialog(QDialog):
    """Диалог «База данных» (первый запуск или смена из меню)."""

    def __init__(self, parent: QWidget | None = None,
                 first_run: bool = False) -> None:
        super().__init__(parent)
        self._first_run = first_run
        self.setWindowTitle(
            "Подключение к базе данных" if first_run else "База данных"
        )
        self.setMinimumWidth(580)

        # --- локальная база -------------------------------------------------
        self.rb_local = QRadioButton(
            "Локальная база (файл SQLite на этом компьютере)"
        )
        self.rb_local.setChecked(True)

        self.ed_path = QLineEdit(str(db.DB_PATH))
        btn_browse = QPushButton("Обзор…")
        btn_browse.clicked.connect(self._browse_sqlite)
        path_row = QHBoxLayout()
        path_row.addWidget(self.ed_path, 1)
        path_row.addWidget(btn_browse)

        # --- серверная база --------------------------------------------------
        self.rb_server = QRadioButton(
            "Серверная база данных (PostgreSQL / MySQL / MariaDB)"
        )

        self.cb_backend = QComboBox()
        for name, dialect, _port in BACKENDS:
            self.cb_backend.addItem(name, dialect)
        self.cb_backend.currentIndexChanged.connect(self._backend_changed)

        self.ed_host = QLineEdit()
        self.ed_host.setPlaceholderText("например: 10.0.0.5 или db.example.com")
        self.sp_port = QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.ed_database = QLineEdit()
        self.ed_database.setPlaceholderText("имя базы данных на сервере")
        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("пользователь СУБД")
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password.setPlaceholderText("пароль")
        self._backend_changed()

        form = QFormLayout()
        form.addRow("СУБД:", self.cb_backend)
        form.addRow("Сервер (host):", self.ed_host)
        form.addRow("Порт:", self.sp_port)
        form.addRow("Имя базы:", self.ed_database)
        form.addRow("Пользователь:", self.ed_user)
        form.addRow("Пароль:", self.ed_password)

        # --- панели, переключаемые радио-кнопками ----------------------------
        group = QButtonGroup(self)
        group.addButton(self.rb_local)
        group.addButton(self.rb_server)
        self.rb_local.toggled.connect(self._mode_changed)

        self.panel_local = QWidget()
        lay_local = QVBoxLayout(self.panel_local)
        lay_local.setContentsMargins(24, 0, 0, 0)
        lay_local.addLayout(path_row)

        self.panel_server = QWidget()
        lay_server = QVBoxLayout(self.panel_server)
        lay_server.setContentsMargins(24, 0, 0, 0)
        lay_server.addLayout(form)

        hint = QLabel(
            "Таблицы создадутся автоматически при первом подключении. "
            "Настройки сохраняются в файле: " + str(db.config_target())
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #777;")

        drv = QLabel(DRIVER_HINT)
        drv.setWordWrap(True)
        drv.setStyleSheet("color: #777; font-size: 9pt;")

        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet(
            "color: #b3261e; background: #fdecea; padding: 6px; "
            "border-radius: 4px;"
        )
        self.lbl_error.hide()

        buttons = QDialogButtonBox()
        b_ok = buttons.addButton(
            "Проверить и сохранить", QDialogButtonBox.ButtonRole.AcceptRole
        )
        b_cancel = buttons.addButton(
            "Отмена", QDialogButtonBox.ButtonRole.RejectRole
        )
        b_ok.clicked.connect(self._on_save)
        b_cancel.clicked.connect(self.reject)

        lay = QVBoxLayout(self)
        if first_run:
            title = QLabel("Первичная настройка базы данных")
            title.setStyleSheet("font-size: 13pt; font-weight: bold;")
            sub = QLabel(
                "Укажите, где программа будет хранить данные судов, "
                "имущества и актов осмотра."
            )
            sub.setWordWrap(True)
            lay.addWidget(title)
            lay.addWidget(sub)
            lay.addSpacing(8)
        lay.addWidget(self.rb_local)
        lay.addWidget(self.panel_local)
        lay.addWidget(self.rb_server)
        lay.addWidget(self.panel_server)
        lay.addWidget(hint)
        lay.addWidget(drv)
        lay.addWidget(self.lbl_error)
        lay.addWidget(buttons)

        self._mode_changed()

    # ------------------------------------------------------------------
    # Поведение формы
    # ------------------------------------------------------------------

    def _backend_changed(self) -> None:
        backend = self.cb_backend.currentData()
        for _name, dialect, port in BACKENDS:
            if dialect == backend:
                self.sp_port.setValue(port)
                break

    def _mode_changed(self, *_args) -> None:
        local = self.rb_local.isChecked()
        self.panel_local.setVisible(local)
        self.panel_server.setVisible(not local)
        self._set_error(None)

    def _browse_sqlite(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Файл локальной базы данных",
            str(self.ed_path.text()),
            "База SQLite (*.db);;Все файлы (*)",
        )
        if path:
            self.ed_path.setText(path)

    def _set_error(self, message: str | None) -> None:
        if message:
            self.lbl_error.setText(message)
            self.lbl_error.show()
        else:
            self.lbl_error.clear()
            self.lbl_error.hide()

    # ------------------------------------------------------------------
    # Сбор настроек и подключение
    # ------------------------------------------------------------------

    def collect_url(self) -> str:
        """URL по текущему выбору в форме (без подключения)."""
        if self.rb_local.isChecked():
            path = self.ed_path.text().strip()
            if not path:
                raise ValueError("Укажите путь к файлу локальной базы данных.")
            return db._sqlite_url(Path(path).expanduser())
        return compose_server_url(
            backend_key=self.cb_backend.currentData(),
            host=self.ed_host.text(),
            port=self.sp_port.value(),
            database=self.ed_database.text(),
            user=self.ed_user.text(),
            password=self.ed_password.text(),
        )

    def collect_settings(self) -> dict[str, str]:
        """Записи для файла окружения по текущей форме."""
        if self.rb_local.isChecked():
            path = Path(self.ed_path.text().strip()).expanduser()
            return {"BOATAPP_DB": str(path)}
        return {"BOATAPP_DB_URL": self.collect_url()}

    def try_connect(self) -> tuple[bool, str]:
        """Пробует подключиться и создать схему (без сохранения файла).

        Возвращает (успех, описание или текст ошибки). При успехе активная
        база программы уже переключена.
        """
        try:
            url = self.collect_url()
        except ValueError as exc:
            return False, str(exc)
        try:
            desc = db.activate_database(url)
        except Exception as exc:
            return False, str(exc)
        return True, desc

    def _on_save(self) -> None:
        success, text = self.try_connect()
        if not success:
            self._set_error(text)
            return
        # подключение установлено и схема создана — сохраняем настройки
        try:
            db.save_database_config(self.collect_settings())
        except OSError as exc:  # pragma: no cover
            QMessageBox.warning(
                self,
                "База данных",
                "Подключение установлено, но не удалось сохранить настройки"
                f" в файл:\n{exc}\n\n"
                "Настройку нужно будет повторить при следующем запуске.",
            )
        self._set_error(None)
        self.accept()


def run_db_setup_dialog(parent: QWidget | None = None,
                        first_run: bool = False) -> bool:
    """Показывает диалог настройки. True — настройка сохранена и применена."""
    dlg = DbSetupDialog(parent, first_run=first_run)
    return dlg.exec() == QDialog.DialogCode.Accepted
