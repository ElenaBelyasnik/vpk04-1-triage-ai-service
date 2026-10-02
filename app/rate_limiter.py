"""
app/rate_limiter.py — лимитирование запросов (этап 2: ЗАГЛУШКА).

На этом этапе лимитирование НЕ подключается.
Функция is_allowed всегда разрешает запрос. Настройка
config.RATE_LIMIT_PER_MINUTE уже загружена из .env и будет
использована на следующем этапе (например, скользящее окно на client_id).
"""

from app import config  # RATE_LIMIT_PER_MINUTE пригодится на следующем этапе
from app.logger import setup_logger  # общий логгер приложения

logger = setup_logger("triage.rate_limiter")


def is_allowed(client_id: str) -> bool:
    """
    Заглушка проверки лимита запросов.

    Сейчас: всегда True (лимиты не применяются).
    Позже: подсчёт запросов клиента за минуту и сравнение
    с config.RATE_LIMIT_PER_MINUTE.
    """
    # Явно показываем в логе, что проверка пройдена «всегда».
    logger.debug(
        "RateLimiter (заглушка): запрос разрешён для client_id=%s (лимит/мин=%s)",
        client_id,
        config.RATE_LIMIT_PER_MINUTE,
    )
    return True
