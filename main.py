"""
main.py — точка входа FastAPI-приложения Triage AI Service.

Запуск из корня проекта:
    uvicorn main:app --reload

После запуска:
- Swagger UI: http://localhost:8000/docs
- Эндпоинт:  POST http://localhost:8000/triage
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI  # основной класс приложения

from app.api import router  # роутер с эндпоинтом POST /triage
from app.config import DB_PATH  # путь к файлу БД (для сообщения в логе)
from app.database import init_db  # создание файла БД и таблицы tickets
from app.logger import setup_logger  # настройка логирования


# Настраиваем логирование ДО создания приложения, чтобы
# стартовые сообщения уже писались в консоль и logs/app.log.
logger = setup_logger("triage.main")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Жизненный цикл приложения.

    До приёма первых запросов готовим хранилище: создаём файл БД и таблицу
    tickets. Без этого шага первая же запись упалась бы с «no such table:
    tickets», ошибка перехватилась бы и аудит обращений молча терялся бы —
    поэтому инициализация выполняется на старте, а не «когда-нибудь потом».

    Ошибка инициализации не роняет сервис: обращения продолжают
    обрабатываться, а о невозможности вести аудит сообщает предупреждение в логе.
    """
    try:
        init_db()
        logger.info("Хранилище готово к работе: %s", DB_PATH)
    except Exception as exc:  # noqa: BLE001 — старт не должен падать из-за хранилища
        logger.warning(
            "Не удалось инициализировать хранилище %s (%s: %s) — обращения "
            "обрабатываются, но аудит может не сохраняться",
            DB_PATH,
            type(exc).__name__,
            exc,
        )

    yield  # приложение работает и обрабатывает запросы


# Создаём приложение с коротким описанием (видно в Swagger UI).
app = FastAPI(
    title="Triage AI Service",
    description="MVP-сервис предварительной обработки клиентских обращений (триаж).",
    version="0.1.0",
    lifespan=lifespan,
)

# Подключаем роутер: эндпоинт POST /triage становится доступен в приложении.
app.include_router(router)

# Сообщение о успешном запуске — в лог и в консоль.
logger.info("Сервис запущен: http://localhost:8000/docs")
print("Сервис запущен: http://localhost:8000/docs")
