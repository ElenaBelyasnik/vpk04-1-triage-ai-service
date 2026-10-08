"""
app/api.py — роутер с эндпоинтом POST /triage.

Здесь сосредоточена логика приёма обращения:
1) FastAPI валидирует вход моделью TriageRequest (ошибка -> 422);
2) (заглушка) проверяется лимит запросов;
3) LLM определяет категорию и готовит черновик ответа (этап 3);
4) обращение и результат сохраняются в SQLite (этап 4);
5) возвращается TriageResponse.
"""

from fastapi import APIRouter  # роутер для подключения к главному приложению

from app import config  # MAX_TEXT_LENGTH — для лога лимитов
from app.database import save_ticket  # сохранение обращений в SQLite (этап 4)
from app.llm_service import (  # LLM-сервис, его fallback и версия с причиной ошибки
    FALLBACK,
    triage_text_with_error,
)
from app.logger import setup_logger  # общий логгер приложения
from app.models import TriageRequest, TriageResponse  # контракт API
from app.rate_limiter import is_allowed  # заглушка лимитирования

# Роутер вынесен в отдельный модуль — main.py только подключает его.
router = APIRouter()

logger = setup_logger("triage.api")

# Ограничение на длину текста ошибки, который кладём в колонку error.
# Сообщения провайдера бывают длинными, а строки лога и БД должны оставаться
# читаемыми; для аудита достаточно начала сообщения (причину видно по нему).
MAX_ERROR_LENGTH = 500


@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest) -> TriageResponse:
    """
    Обработка входящего обращения (триаж).

    Принимает JSON: text, channel, client_id.
    Возвращает JSON: category, draft_reply, confidence, escalate.
    Невалидные данные отклоняются автоматически (422) до входа в функцию.
    Обращение и результат пишутся в таблицу tickets (аудит).
    """
    # Логируем факт запроса: client_id, channel и длина text (без самого
    # текста — персональные данные клиента не должны попадать в логи).
    logger.info(
        "POST /triage: client_id=%s, channel=%s, длина text=%s (лимит=%s)",
        request.client_id,
        request.channel,
        len(request.text),
        config.MAX_TEXT_LENGTH,
    )

    # Шаг 1. Лимитирование (заглушка — всегда разрешает).
    if not is_allowed(request.client_id):
        # На этом этапе недостижимо, но ветка закладывается заранее:
        # позже здесь будет исключение 429 Too Many Requests.
        logger.warning("RateLimiter отклонил запрос client_id=%s", request.client_id)
        raise NotImplementedError("Лимитирование будет подключено на следующем этапе")

    # Шаг 2. LLM-обработка: классификация + черновик ответа.
    # llm_error — причина, по которой результат мог стать fallback-ом: она
    # уходит в колонку error таблицы tickets. None означает «LLM отработала штатно».
    llm_error: str | None = None
    try:
        # triage_text_with_error не бросает исключений и всегда возвращает
        # пару (результат, причина ошибки). triage_text сам по себе не бросает
        # исключений, но try/except оставляем как второй слой защиты: сюда
        # могут прийти нештатные ситуации вроде ошибки распаковки dict в модель.
        result, llm_error = triage_text_with_error(
            text=request.text,
            channel=request.channel,
        )
        response = TriageResponse(**result)
    except Exception as exc:  # noqa: BLE001 — наружу не пускаем 500 из-за LLM
        logger.error(
            "LLM вернула ошибку для client_id=%s: %s: %s — отдаю fallback",
            request.client_id,
            type(exc).__name__,
            exc,
        )
        # Fallback из llm_service: category=other, confidence=low,
        # escalate=True, draft_reply="Обращение передано оператору."
        response = TriageResponse(**FALLBACK)
        # Причину тоже записываем: в БД должно быть видно, что это не ответ модели.
        llm_error = f"{type(exc).__name__}: {exc}"

    # Шаг 3. Сохранение обращения и результата в SQLite (аудит).
    # save_ticket перехватывает ошибки БД сам и возвращает None при неудаче,
    # поэтому ответ клиенту не ломается, а факт сохранения/ошибки виден в логе.
    # Поля берём из response — так в БД попадает ровно то, что увидел клиент.
    ticket_id = save_ticket(
        client_id=request.client_id,
        channel=request.channel,
        text=request.text,
        category=response.category,
        confidence=response.confidence,
        escalate=response.escalate,
        draft_reply=response.draft_reply,
        error=llm_error[:MAX_ERROR_LENGTH] if llm_error else None,
    )

    logger.info(
        "POST /triage: ответ для client_id=%s — category=%s, confidence=%s, escalate=%s, ticket_id=%s",
        request.client_id,
        response.category,
        response.confidence,
        response.escalate,
        ticket_id,
    )

    # response_model=TriageResponse гарантирует соответствие контракту.
    return response
