"""
app/api.py — роутер с эндпоинтом POST /triage.

Здесь сосредоточена логика приёма обращения:
1) FastAPI валидирует вход моделью TriageRequest (ошибка -> 422);
2) (заглушка) проверяется лимит запросов;
3) LLM определяет категорию и готовит черновик ответа (этап 3);
4) (заглушка) обращение сохраняется в БД;
5) возвращается TriageResponse.
"""

from fastapi import APIRouter  # роутер для подключения к главному приложению

from app import config  # MAX_TEXT_LENGTH — для лога лимитов
from app.database import save_request  # заглушка БД
from app.llm_service import FALLBACK, triage_text  # LLM-сервис и его fallback
from app.logger import setup_logger  # общий логгер приложения
from app.models import TriageRequest, TriageResponse  # контракт API
from app.rate_limiter import is_allowed  # заглушка лимитирования

# Роутер вынесен в отдельный модуль — main.py только подключает его.
router = APIRouter()

logger = setup_logger("triage.api")


@router.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest) -> TriageResponse:
    """
    Обработка входящего обращения (триаж).

    Принимает JSON: text, channel, client_id.
    Возвращает JSON: category, draft_reply, confidence, escalate.
    Невалидные данные отклоняются автоматически (422) до входа в функцию.
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
    # triage_text сам по себе не бросает исключений (внутри него — fallback),
    # но try/except оставляем как второй слой защиты: сюда могут прийти
    # нештатные ситуации вроде ошибки распаковки dict в модель ответа.
    try:
        result = triage_text(text=request.text, channel=request.channel)
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

    # Шаг 3. Сохранение обращения (заглушка БД — только лог).
    save_request(
        client_id=request.client_id,
        channel=request.channel,
        text=request.text,
    )

    logger.info(
        "POST /triage: ответ для client_id=%s — category=%s, confidence=%s, escalate=%s",
        request.client_id,
        response.category,
        response.confidence,
        response.escalate,
    )

    # response_model=TriageResponse гарантирует соответствие контракту.
    return response
