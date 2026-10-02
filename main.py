"""
main.py — точка входа FastAPI-приложения Triage AI Service.

Запуск из корня проекта:
    uvicorn main:app --reload

После запуска:
- Swagger UI: http://localhost:8000/docs
- Эндпоинт:  POST http://localhost:8000/triage
"""

from fastapi import FastAPI  # основной класс приложения

from app.api import router  # роутер с эндпоинтом POST /triage
from app.logger import setup_logger  # настройка логирования

# Настраиваем логирование ДО создания приложения, чтобы
# стартовые сообщения уже писались в консоль и logs/app.log.
logger = setup_logger("triage.main")

# Создаём приложение с коротким описанием (видно в Swagger UI).
app = FastAPI(
    title="Triage AI Service",
    description="MVP-сервис предварительной обработки клиентских обращений (триаж).",
    version="0.1.0",
)

# Подключаем роутер: эндпоинт POST /triage становится доступен в приложении.
app.include_router(router)

# Сообщение о успешном запуске — в лог и в консоль.
logger.info("Сервис запущен: http://localhost:8000/docs")
print("Сервис запущен: http://localhost:8000/docs")
