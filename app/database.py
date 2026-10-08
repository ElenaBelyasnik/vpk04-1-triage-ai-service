"""
app/database.py — хранение обращений в SQLite (этап 4).

Здесь сосредоточена вся работа с базой данных: схема, соединение, запись
и чтение. Наружу торчат три функции:

    init_db()                — создать файл БД и таблицу tickets (старт сервиса);
    save_ticket(...)         — сохранить обращение, вернуть id новой строки;
    get_ticket(ticket_id)    — прочитать одну запись по id (для проверки).

Почему sqlite3, а не SQLAlchemy: это стандартная библиотека Python, ТЗ
требует именно её, и в requirements.txt не появляется лишних пакетов.

Почему соединение открывается на каждую операцию: сервис работает в одном
процессе, операций немного, а короткое соединение снимает сразу несколько
вопросов — «безопасно ли это из потока uvicorn», «не потеряем ли данные при
ошибке», «что будет при --reload». Открытие файла SQLite стоит доли
миллисекунды, экономить на нём не будем.

Ошибки БД наружу НЕ выпускаем: обращение уже обработано и ответ клиенту
готов, поэтому падать с 500 из-за проблем хранилища — значит ломать то, что
важнее. Факт ошибки пишем в лог уровнем ERROR, ответ отдаём.
"""

import sqlite3  # стандартная библиотека SQLite — без внешних зависимостей
from pathlib import Path  # разрешение пути к файлу БД

from app import config  # DB_PATH — путь к файлу базы из .env
from app.logger import setup_logger  # общий логгер приложения

logger = setup_logger("triage.database")

# Корень проекта: app/database.py -> app/ -> корень. Нужен, чтобы относительный
# DB_PATH не зависел от текущей директории, из которой запустили uvicorn.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Схема таблицы — ровно по ТЗ. Два уточнения, которые оставлены как в ТЗ:
#   * created_at подставляет сам SQLite (CURRENT_TIMESTAMP), приложению не
#     нужно следить за часовой зоной и форматом даты;
#   * CHECK-ограничения не добавляем: допустимые значения channel/category/
#     confidence держит контракт app/models.py, а лишний CHECK плодил бы
#     ошибки при расширении списков.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    client_id   TEXT    NOT NULL,
    channel     TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    category    TEXT,
    confidence  TEXT,
    escalate    INTEGER,
    draft_reply TEXT,
    error       TEXT
)
"""

# Вставка одной строки. created_at не перечислен — его подставит схема.
# Все значения идут параметрами (?), конкатенации SQL нет: кавычки и точки
# с запятой в тексте обращения остаются текстом, а не командами.
_INSERT_SQL = """
INSERT INTO tickets
    (client_id, channel, text, category, confidence, escalate, draft_reply, error)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

# Чтение по id — для ручной проверки записи после запроса.
_SELECT_BY_ID_SQL = "SELECT * FROM tickets WHERE id = ?"


def _resolve_db_path() -> Path:
    """
    Превратить значение DB_PATH в конкретный путь к файлу.

    Относительный путь («tickets.db») разрешаем от корня проекта, а не от
    текущей директории: так файл оказывается в корне и при запуске
    «uvicorn main:app --reload» из корня, и из другого каталога.
    Абсолютный путь (например, DB_PATH=D:/data/tickets.db) используем как есть.
    """
    path = Path(config.DB_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _connect() -> sqlite3.Connection:
    """
    Открыть соединение с базой и настроить его под приложение.

    Родительскую папку создаём сами: SQLite создаёт только файл, но не
    каталоги, иначе первая запись в DB_PATH=data/tickets.db упала бы ошибкой.
    """
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path))

    # RowFactory даёт доступ к колонкам по имени (row["category"]) — читаемый
    # результат без ручного сопоставления позиций колонок.
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """
    Инициализировать базу: создать файл и таблицу tickets.

    Вызывается один раз при старте приложения (main.py). Идемпотентно
    благодаря «IF NOT EXISTS»: повторный запуск существующие строки не трогает.

    Ошибку логируем, но не пробрасываем: сервис должен остаться живым, даже
    если хранилище недоступно (нет прав, диск занят, путь кривой).
    """
    try:
        connection = _connect()
        try:
            connection.execute(_CREATE_TABLE_SQL)
            connection.commit()
        finally:
            connection.close()
    except Exception as exc:  # noqa: BLE001 — старт не должен падать из-за БД
        logger.error(
            "Не удалось инициализировать БД (%s): %s: %s",
            _resolve_db_path(),
            type(exc).__name__,
            exc,
        )
        return

    logger.info("БД готова: файл=%s, таблица=tickets", _resolve_db_path())


def save_ticket(
    *,
    client_id: str,
    channel: str,
    text: str,
    category: str | None = None,
    confidence: str | None = None,
    escalate: bool | None = None,
    draft_reply: str | None = None,
    error: str | None = None,
) -> int | None:
    """
    Сохранить обращение и результат триажа, вернуть id новой строки.

    Аргументы только по имени (*) — вызывающий явно перечисляет поля, и
    перепутать местами channel с text невозможно.

    Возвращает id вставленной строки либо None, если запись не удалась.
    None — не исключение: вызывающий спокойно продолжит отдавать клиенту
    уже готовый ответ.
    """
    try:
        connection = _connect()
        try:
            cursor = connection.execute(
                _INSERT_SQL,
                (
                    client_id,
                    channel,
                    text,
                    category,
                    confidence,
                    # SQLite хранит булев флаг как INTEGER 0/1. None остаётся
                    # NULL — это случай «результат не получен», отличается от 0.
                    None if escalate is None else int(escalate),
                    draft_reply,
                    error,
                ),
            )
            connection.commit()
        finally:
            # Закрываем соединение в любом случае — и при успехе, и при ошибке.
            connection.close()
    except Exception as exc:  # noqa: BLE001 — ответ клиенту важнее записи в БД
        # Хранилище недоступно, но обращение-то обработано. Ответ не ломаем,
        # факт потери записи фиксируем уровнем ERROR (виден при любом LOG_LEVEL).
        logger.error(
            "Не удалось сохранить обращение в БД (client_id=%s): %s: %s",
            client_id,
            type(exc).__name__,
            exc,
        )
        return None

    ticket_id = cursor.lastrowid

    # Факт сохранения — INFO: по этим строкам сверяется, что аудит пишется.
    # id попадает в лог, чтобы связать строку в БД с конкретным запросом.
    # Сам текст обращения в лог не пишем — это персональные данные клиента.
    logger.info(
        "Обращение сохранено в БД: id=%s, client_id=%s, channel=%s, "
        "category=%s, confidence=%s, escalate=%s, error=%s",
        ticket_id,
        client_id,
        channel,
        category,
        confidence,
        escalate,
        bool(error),
    )
    return ticket_id


def get_ticket(ticket_id: int) -> dict | None:
    """
    Прочитать обращение по id.

    Нужен для ручной проверки: отправил запрос → получил id из лога → достал
    строку из БД и сверил поля. Возвращает dict (удобно печатать и отдавать
    в JSON) либо None, если записи с таким id нет.
    """
    try:
        connection = _connect()
        try:
            cursor = connection.execute(_SELECT_BY_ID_SQL, (ticket_id,))
            row = cursor.fetchone()
        finally:
            connection.close()
    except Exception as exc:  # noqa: BLE001 — чтение не должно ронять сервис
        logger.error(
            "Не удалось прочитать обращение id=%s из БД: %s: %s",
            ticket_id,
            type(exc).__name__,
            exc,
        )
        return None

    # dict(row): sqlite3.Row — курсор-подобный объект, а нужен обычный словарь,
    # который можно сериализовать в JSON или распечатать.
    return dict(row) if row is not None else None
