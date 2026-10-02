"""
app/config.py — загрузка настроек из файла .env.

Модуль читает переменные окружения через python-dotenv, приводит их
к нужным типам и проверяет наличие обязательных значений при импорте.
Доступ к настройкам — через модульные константы (MAX_TEXT_LENGTH, LOG_LEVEL и т.д.).
"""

import os  # доступ к переменным окружения

from dotenv import load_dotenv  # загрузка переменных из файла .env

# Загружаем .env из корня проекта.
# Путь строим от расположения этого файла: app/config.py -> корень на уровень выше.
load_dotenv()

# --- Обязательные переменные -------------------------------------------------

# Ключ к прокси-API (OpenAI-совместимый сервис). На этапе заглушки не
# используется по назначению, но должен присутствовать в .env.
PROXY_API_KEY = os.getenv("PROXY_API_KEY")

# Базовый URL API (например, https://api.proxyapi.ru/v1).
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# Название модели, которая будет использоваться на следующих этапах.
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

# --- Необязательные переменные со значениями по умолчанию --------------------


def _get_float(name: str, default: float) -> float:
    """Читает переменную окружения как float; при ошибке/отсутствии — default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        # Некорректное значение не роняем — берём значение по умолчанию.
        return default


def _get_int(name: str, default: int) -> int:
    """Читает переменную окружения как int; при ошибке/отсутствии — default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Температура генерации LLM (влияет на «креативность» ответов модели).
# ВАЖНО: параметр ПЕРЕДАЁТСЯ в запросы к LLM (для гибкости при смене
# модели/провайдера). Модель openai/gpt-5.6-luna через ProxyAPI не
# поддерживает temperature (провайдер использует дефолт 1), но если
# провайдер ответит ошибкой 400 — запрос повторится без него (этап 3).
TEMPERATURE: float = _get_float("TEMPERATURE", 0.2)

# Максимум запросов в минуту на клиента (пригодится на этапе лимитирования).
RATE_LIMIT_PER_MINUTE: int = _get_int("RATE_LIMIT_PER_MINUTE", 5)

# Максимальная длина текста обращения (используется валидацией моделей).
MAX_TEXT_LENGTH: int = _get_int("MAX_TEXT_LENGTH", 2000)

# Уровень логирования: DEBUG / INFO / WARNING / ERROR / CRITICAL.
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# --- Проверка обязательных переменных ----------------------------------------

# Собираем имена переменных, которые оказались пустыми/отсутствующими.
_missing = [
    name
    for name, value in {
        "PROXY_API_KEY": PROXY_API_KEY,
        "OPENAI_BASE_URL": OPENAI_BASE_URL,
        "OPENAI_MODEL": OPENAI_MODEL,
    }.items()
    if not value
]

if _missing:
    # Если обязательных переменных нет — приложение не должно запускаться:
    # это явная ошибка конфигурации, а не runtime-ситуация.
    raise RuntimeError(
        "Не заданы обязательные переменные окружения: "
        + ", ".join(_missing)
        + ". Проверьте файл .env (образец — в .env.example)."
    )
