# Triage AI Service

MVP-сервис на FastAPI для предварительной обработки (триажа) клиентских
обращений: приём обращения по API, определение категории и подготовка
черновика ответа.

## Текущее состояние

- **Этап 2 завершён** (подтверждён ручным тестированием через Swagger UI):
  реализован эндпоинт `POST /triage` с полной валидацией входных данных
  (Pydantic) и логированием в консоль и `logs/app.log`.
- LLM, база данных и лимитирование запросов **не подключены** — используются
  заглушки.
- **Следующий шаг — этап 3: подключение LLM через ProxyAPI** (с fallback при
  неподдерживаемом `temperature`). Подробный план передачи — в
  `ProgressOfWork.md`.

## Запуск

```bash
# 1. Создать и активировать виртуальное окружение
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Создать .env из образца и заполнить ключи
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/macOS

# 4. Запустить сервис
uvicorn main:app --reload
```

## Проверка

- Swagger UI: http://localhost:8000/docs
- Примеры HTTP-запросов: `tests/test_requests.http`

## Ограничения провайдера

**Модель `openai/gpt-5.6-luna` через ProxyAPI не поддерживает настройку
параметра `temperature`** — провайдер использует дефолтное значение (1).
Однако параметр передаётся в запрос: если модель или провайдер поменяются
на поддерживающие `temperature`, оно заработает автоматически. При ошибке
400 из-за `temperature` запрос повторяется без этого параметра.

## Пример запроса

```json
POST /triage
{
  "text": "Не приходит счёт за услуги",
  "channel": "email",
  "client_id": "client-001"
}
```

## Пример ответа

```json
{
  "category": "other",
  "draft_reply": "Обращение получено, обрабатывается.",
  "confidence": "low",
  "escalate": true
}
```
