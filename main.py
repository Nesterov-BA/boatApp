"""Точка входа программы «АСИ — учёт и проверка имущества на судах».

Запуск из каталога проекта:

    uv run python main.py

или после установки пакета — командой ``boatapp``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Пакет лежит в src/, а точка входа — в корне проекта:
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from boatapp import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
