"""Подключение к базе данных: локальный SQLite или удалённый сервер.

Настройка выполняется в графическом диалоге при первом запуске (см.
``boatapp.db_setup``) и сохраняется в файл окружения ``boatapp.env``:

* рядом с приложением (каталог проекта), если он доступен для записи, иначе
* в пользовательском каталоге конфигурации (BoatApp).

Остаются и «продвинутые» способы (они имеют приоритет над файлом):
переменная ``BOATAPP_DB_URL``, путь SQLite через ``BOATAPP_DB`` и аргумент
командной строки ``--db-url``.

Движок можно переключить в рантайме через ``activate_database()`` — это
использует диалог настройки, чтобы не требовать перезапуска.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# --------------------------------------------------------------------------
# Файл окружения и его расположение
# --------------------------------------------------------------------------


def _user_config_dir() -> Path:
    """Пользовательский каталог конфигурации приложения (без Qt)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(
            Path.home() / "AppData" / "Roaming"
        )
    elif sys.platform == "darwin":
        base = os.environ.get("XDG_CONFIG_HOME") or str(
            Path.home() / "Library" / "Application Support"
        )
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "BoatApp"


USER_CONFIG_FILE: Path = _user_config_dir() / "boatapp.env"


def _env_file_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("BOATAPP_ENV_FILE", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(PROJECT_ROOT / "boatapp.env")
    candidates.append(Path.cwd() / "boatapp.env")
    candidates.append(USER_CONFIG_FILE)
    return candidates


def find_env_file() -> Path | None:
    """Первый существующий файл окружения (или None)."""
    for path in _env_file_candidates():
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _load_env_file() -> None:
    path = find_env_file()
    if path is None:
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def config_target() -> Path:
    """Куда будет сохранена настройка: рядом с приложением или у пользователя."""
    explicit = os.environ.get("BOATAPP_ENV_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    existing = find_env_file()
    if existing is not None:
        return existing
    project_file = PROJECT_ROOT / "boatapp.env"
    if os.access(PROJECT_ROOT, os.W_OK):
        return project_file
    return USER_CONFIG_FILE


def save_database_config(values: dict[str, str], target: Path | None = None) -> Path:
    """Сохраняет КЛЮЧ=значение в файл окружения. Возвращает путь к файлу."""
    file = target or config_target()
    file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Файл настроек программы «АСИ». Создан автоматически.\n",
        "# Содержит параметры подключения к базе данных.\n",
    ]
    for key, value in values.items():
        value = value.replace("\n", "").replace("\r", "")
        lines.append(f"{key}={value}\n")
    file.write_text("".join(lines), encoding="utf-8")
    return file


def configured_url() -> str | None:
    """Полный URL серверной базы данных из окружения (или None)."""
    value = os.environ.get("BOATAPP_DB_URL", "").strip()
    return value or None


def has_explicit_config() -> bool:
    """Есть ли уже настроенная база (файл/переменные) — диалог не нужен."""
    if configured_url():
        return True
    if os.environ.get("BOATAPP_DB", "").strip():
        return True
    return find_env_file() is not None


def default_db_path() -> Path:
    """Путь к файлу локального SQLite (если сервер не задан)."""
    env = os.environ.get("BOATAPP_DB", "").strip()
    if env:
        return Path(env).expanduser()
    return PROJECT_ROOT / "boatapp.db"


DB_PATH: Path = default_db_path()

# --------------------------------------------------------------------------
# Диагностика (определяется до создания движка)
# --------------------------------------------------------------------------

_DRIVER_HINTS: dict[str, str] = {
    "postgresql": 'установите драйвер:  uv add "psycopg[binary]"',
    "mysql": "установите драйвер:  uv add pymysql",
    "mariadb": "установите драйвер:  uv add pymysql",
    "mssql": "установите драйвер:  uv add pyodbc",
}


def _sqlite_url(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    return f"sqlite:///{text}"


def _describe_url(url: str) -> str:
    try:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            database = parsed.database or DB_PATH.name
            return f"диалект: sqlite · файл: {database}"
        backend = parsed.get_backend_name()
        where = parsed.host or ""
        if parsed.port:
            where += f":{parsed.port}"
        if parsed.database:
            where += f"/{parsed.database}"
        return f"диалект: {backend} · сервер: {where}"
    except Exception:
        return "диалект не определён"


def safe_url_text(url: str) -> str:
    """URL для показа пользователю — без пароля."""
    try:
        parsed = make_url(url)
        if parsed.password:
            parsed = parsed.set(password="****")
        return str(parsed)
    except Exception:
        return "(не удалось разобрать URL базы данных)"


def _connect_error_hint(url: str, exc: Exception) -> str:
    """Понятное сообщение об ошибке подключения с подсказкой по драйверу."""
    hint = ""
    try:
        backend = make_url(url).get_backend_name()
        hint = _DRIVER_HINTS.get(backend, "")
    except Exception:
        pass

    driver_msg = ""
    if isinstance(exc, ModuleNotFoundError) and hint:
        driver_msg = f"\nПохоже, не установлен драйвер СУБД — {hint}."
    elif isinstance(exc, ModuleNotFoundError):
        driver_msg = f"\nНе установлен модуль: {exc.name}."

    return (
        "Не удалось подключиться к базе данных.\n"
        f"URL: {safe_url_text(url)}\n"
        f"{_describe_url(url)}\n\n"
        f"Ошибка: {exc}{driver_msg}"
    )


# --------------------------------------------------------------------------
# Движок
# --------------------------------------------------------------------------


def _sqlite_pragma(dbapi_connection, _connection_record) -> None:
    """Включаем внешние ключи и WAL (только для SQLite)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def build_engine(url: str):
    """Создаёт движок SQLAlchemy для указанного URL.

    Если драйвер СУБД не установлен — бросает RuntimeError с подсказкой,
    какой драйвер нужно поставить (вместо голого ModuleNotFoundError).
    """
    if not url:
        url = _sqlite_url(DB_PATH)

    if make_url(url).get_backend_name() == "sqlite":
        engine = create_engine(url)
        event.listen(engine, "connect", _sqlite_pragma)
        return engine

    # Серверная база: переживаем обрыв сети, не держим протухшие сессии
    options: dict = {"pool_pre_ping": True, "pool_recycle": 1800}
    backend = make_url(url).get_backend_name()
    if backend in ("postgresql", "mysql", "mariadb"):
        options["connect_args"] = {"connect_timeout": 15}

    try:
        return create_engine(url, **options)
    except ModuleNotFoundError as exc:
        raise RuntimeError(_connect_error_hint(url, exc)) from exc


# Активный URL и движок. Начальное значение — по настройкам окружения/файла,
# дальше может быть переключено диалогом настройки (без перезапуска).
def _initial_url() -> str:
    url = configured_url()
    if url:
        return url
    return _sqlite_url(DB_PATH)


ACTIVE_URL: str = _initial_url()
engine = build_engine(ACTIVE_URL)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

# --------------------------------------------------------------------------
# Переключение базы данных в рантайме
# --------------------------------------------------------------------------


def activate_database(url: str) -> str:
    """Проверяет, создаёт схему и делает *url* активной базой программы.

    Возвращает описание подключения. При неудаче состояние не меняется —
    активной остаётся прежняя база, а ошибка (RuntimeError) содержит
    понятный текст.
    """
    global ACTIVE_URL, engine, DB_PATH

    new_engine = build_engine(url)
    from . import models  # noqa: F401  (регистрирует модели в метаданных)

    try:
        with new_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        Base.metadata.create_all(new_engine)
    except Exception as exc:
        new_engine.dispose()
        raise RuntimeError(_connect_error_hint(url, exc)) from exc

    old_engine = engine
    ACTIVE_URL = url
    engine = new_engine
    SessionLocal.configure(bind=engine)

    if make_url(url).get_backend_name() == "sqlite":
        DB_PATH = Path(make_url(url).database or DB_PATH)

    if old_engine is not engine:
        try:
            old_engine.dispose()
        except Exception:  # pragma: no cover
            pass
    return describe_backend()


def describe_backend() -> str:
    """Короткое описание текущего подключения для пользователя."""
    return _describe_url(ACTIVE_URL)


def safe_database_url() -> str:
    """URL активной базы для показа — без пароля."""
    return safe_url_text(ACTIVE_URL)


def check_connection() -> str:
    """Проверяет связь с базой. Возвращает описание, бросает ошибку иначе."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(_connect_error_hint(ACTIVE_URL, exc)) from exc
    return describe_backend()


def init_db() -> None:
    """Проверяет подключение и создаёт таблицы, если их ещё нет."""
    check_connection()
    Base.metadata.create_all(engine)
