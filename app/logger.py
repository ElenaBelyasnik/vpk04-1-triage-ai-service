"""
app/logger.py — настройка логирования приложения.

Логи пишутся одновременно:
- в консоль (stdout);
- в файл logs/app.log (папка logs/ создаётся автоматически).

Формат: дата, время, уровень, модуль, сообщение.
Уровень берётся из config.LOG_LEVEL (переменная окружения LOG_LEVEL).
Режим записи файла берётся из config.LOG_MODE (переменная LOG_MODE):
- write  (по умолчанию) — файл пересоздаётся при каждом запуске сервиса,
  в логе остаются только записи текущего запуска (удобно отлаживать);
- append — файл дописывается, история сохраняется между запусками.
"""

import logging  # стандартная библиотека логирования Python
from pathlib import Path  # работа с путями и создание папок

from app import config  # уровень и режим логирования из настроек

# Путь к каталогу логов: <корень проекта>/logs
# __file__ -> app/logger.py, parent -> app/, parent.parent -> корень проекта.
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

# Формат записи: дата, время, уровень, имя модуля, сообщение.
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Флаг «файл логов в этом процессе уже создавали». Нужен, потому что
# логгеров несколько (triage.main, triage.api, triage.llm, ...), и каждый
# создаёт свой FileHandler. Если открывать файл с mode="w" каждый раз,
# второй логгер стёр бы записи первого. Поэтому в режиме write файл
# пересоздаётся ровно один раз за запуск процесса, а остальные обработчики
# дописывают его в режиме "a". При uvicorn --reload процесс новый —
# флаг сбрасывается, и лог снова начинается с чистого листа.
_file_ready = False


def _file_mode() -> str:
    """
    Режим открытия файла логов для нового обработчика.

    append -> всегда "a" (накопление).
    write  -> "w" при первом логгере запуска (пересоздание файла),
              далее "a", чтобы не затирать записи уже созданных логгеров.
    """
    global _file_ready

    if config.LOG_MODE == "append":
        return "a"

    mode = "a" if _file_ready else "w"
    _file_ready = True
    return mode


def setup_logger(name: str = "triage") -> logging.Logger:
    """
    Создаёт и настраивает логгер с именем name.

    - Создаёт папку logs/, если её ещё нет.
    - Добавляет два обработчика: консоль и файл.
    - Уровень логирования берётся из config.LOG_LEVEL.
    - Режим файла — из config.LOG_MODE (см. _file_mode).
    """
    # Убеждаемся, что каталог для логов существует (parents=True не роняет
    # исключение, если папка уже есть — exist_ok=True).
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)

    # Уровень из .env; при неизвестном значении fallback на INFO,
    # чтобы опечатка в конфигурации не ломала запуск.
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    # Защита от дублирования обработчиков при повторном вызове
    # (например, при перезагрузке uvicorn --reload).
    if logger.handlers:
        return logger

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # Обработчик №1 — консоль (sys.stderr выбран стандартно для логов).
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Обработчик №2 — файл logs/app.log (кодировка utf-8 для кириллицы).
    # Режим ("w"/"a") выбирает _file_mode в зависимости от LOG_MODE.
    file_handler = logging.FileHandler(LOG_FILE, mode=_file_mode(), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
