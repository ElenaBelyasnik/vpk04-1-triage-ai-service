"""
app/database.py — хранение обращений (этап 2: ЗАГЛУШКА).

На этом этапе база данных SQLite НЕ подключается.
Функция save_request делает «видимость» сохранения: только пишет
в лог информацию о запросе. Реальная таблица появится на следующем этапе.
"""

from app.logger import setup_logger  # общий логгер приложения

logger = setup_logger("triage.database")


def save_request(client_id: str, channel: str, text: str) -> None:
    """
    Заглушка сохранения обращения в базу данных.

    Сейчас: только логирование.
    Позже: вставка строки в SQLite (обращения + результаты триажа).
    """
    # Имитация записи в БД — фиксируем факт в логе.
    logger.info(
        "DB (заглушка): обращение сохранено — client_id=%s, channel=%s, длина text=%s",
        client_id,
        channel,
        len(text),
    )
